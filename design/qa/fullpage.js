// Full-page screenshots with motion off (everything visible): node qa/fullpage.js <outDir> <page> <width> [<width> ...]
const path = require('path');
const { launch, open } = require('./common');
(async () => {
  const [out, name, ...widths] = process.argv.slice(2);
  const browser = await launch();
  for (const w of widths.map(Number)) {
    const { ctx, page } = await open(browser, name, w, { query: 'motion=off' });
    // fixed layers would land in the middle of a full-page capture: leave them out (the tab bar is fixed to the bottom on a phone)
    await page.addStyleTag({ content: '.dpanel, .backtop, .readbar, .tabbar { display: none !important; }' });
    // lazy images below the fold only load when they come near the viewport: make them eager and wait for them (max 5 s)
    await page.evaluate(async () => {
      const imgs = [...document.images];
      imgs.forEach((i) => { i.loading = 'eager'; });
      await Promise.race([
        Promise.all(imgs.map((i) => (i.complete ? null : new Promise((r) => { i.onload = i.onerror = r; })))),
        new Promise((r) => setTimeout(r, 5000)),
      ]);
    });
    await page.waitForTimeout(300);
    const file = path.join(out, `${name}-${w}.png`);
    await page.screenshot({ path: file, fullPage: true });
    const h = await page.evaluate(() => document.documentElement.scrollHeight);
    console.log(`${file}  ${w}x${h}`);
    await ctx.close();
  }
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
