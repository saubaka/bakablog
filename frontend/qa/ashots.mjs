// Screenshots of admin pages. Usage: node qa/ashots.mjs <outDir> <pages comma|all> <widths comma> [full|view]
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { ADMIN_PAGES, BROWSER, launch, openAdmin } from './adminlib.mjs'

const [out, pages = 'all', widths = '390,1280', mode = 'view'] = process.argv.slice(2)
if (!out) { console.error('usage: node qa/ashots.mjs <outDir> <pages|all> <widths> [full|view]'); process.exit(2) }
mkdirSync(out, { recursive: true })
const list = pages === 'all' ? ADMIN_PAGES : pages.split(',').map((n) => ADMIN_PAGES.find(([name]) => name === n)).filter(Boolean)
const browser = await launch()
for (const w of widths.split(',').map(Number)) {
  for (const [name, path] of list) {
    const { ctx, page, errors } = await openAdmin(browser, path, w, { settle: 600 })
    const file = join(out, `${name}-${w}-${BROWSER}.png`)
    await page.screenshot({ path: file, fullPage: mode === 'full' })
    const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
    console.log(`${name}@${w}: ${file} overflow=${over}${errors.length ? ` ERRORS ${JSON.stringify(errors.slice(0, 3))}` : ''}`)
    await ctx.close()
  }
}
await browser.close()
