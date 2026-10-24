// Viewport-sized screenshots at scroll offsets: what a visitor actually sees, fixed layers included.
// Usage: node qa/screens.mjs <outDir> <page> <width> <offsets comma|auto> [query]
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { BROWSER, heightFor, launch, open, settled } from './common.mjs'

const [out, name = 'home', width = '1280', offsetsArg = 'auto', query = 'motion=off'] = process.argv.slice(2)
if (!out) { console.error('usage: node qa/screens.mjs <outDir> <page> <width> <offsets|auto> [query]'); process.exit(2) }
mkdirSync(out, { recursive: true })
const w = Number(width)
const h = heightFor(w)
const browser = await launch()
const { ctx, page, errors } = await open(browser, name, w, { query, settle: 700 })
const total = await page.evaluate(() => document.documentElement.scrollHeight)
const offsets = offsetsArg === 'auto' ? [] : offsetsArg.split(',').map(Number)
if (offsetsArg === 'auto') for (let y = 0; y < total; y += h - 60) offsets.push(y)
let i = 0
for (const y of offsets) {
  await page.evaluate((yy) => window.scrollTo({ top: yy, behavior: 'instant' }), y)
  await settled(page)
  await page.waitForTimeout(60)
  await page.screenshot({ path: join(out, `${name}-${w}-${BROWSER}-${String(i).padStart(2, '0')}.png`) })
  i += 1
}
console.log(`${name}@${w}: total=${total} shots=${offsets.length}${errors.length ? ` ERRORS ${JSON.stringify(errors.slice(0, 3))}` : ''}`)
await ctx.close()
await browser.close()
