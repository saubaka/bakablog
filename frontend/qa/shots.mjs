// Screenshots. Usage: node qa/shots.mjs <outDir> <pages comma|all> <widths comma> [full|view] [query]
//   full: the whole page with motion off (everything visible, fixed layers left out); view: what a visitor sees at the top.
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { PAGES, BROWSER, launch, open } from './common.mjs'

const [out, pages = 'all', widths = '390,768,1280', mode = 'full', query = 'motion=off'] = process.argv.slice(2)
if (!out) { console.error('usage: node qa/shots.mjs <outDir> <pages|all> <widths> [full|view] [query]'); process.exit(2) }
mkdirSync(out, { recursive: true })
const names = pages === 'all' ? PAGES.map((p) => p.name) : pages.split(',')
const browser = await launch()
for (const w of widths.split(',').map(Number)) {
  for (const name of names) {
    const { ctx, page, errors } = await open(browser, name, w, { query, settle: 500 })
    if (mode === 'full') {
      // fixed layers would land in the middle of a full-page capture; lazy pictures only load near the viewport: make them eager
      // (the page's CSP forbids injected <style> elements, so this goes through the CSSOM, like the motion engine does)
      await page.evaluate(async () => {
        document.querySelectorAll('.readbar, .tabbar, .topline, .toc-fab').forEach((e) => e.style.setProperty('display', 'none', 'important'))
        const imgs = [...document.images]
        imgs.forEach((i) => { i.loading = 'eager' })
        await Promise.race([Promise.all(imgs.map((i) => (i.complete ? null : new Promise((r) => { i.onload = i.onerror = r })))), new Promise((r) => setTimeout(r, 5000))])
      })
      await page.waitForTimeout(300)
    }
    const file = join(out, `${name}-${w}-${BROWSER}.png`)
    await page.screenshot({ path: file, fullPage: mode === 'full' })
    const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
    console.log(`${name}@${w} ${BROWSER}: ${file} overflow=${over}${errors.length ? ` ERRORS ${JSON.stringify(errors.slice(0, 3))}` : ''}`)
    await ctx.close()
  }
}
await browser.close()
