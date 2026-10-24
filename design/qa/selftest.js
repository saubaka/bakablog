// Runs the "运行自检" button on the fx lab in a real browser and prints the report.
const { launch, open } = require('./common');
(async () => {
  const browser = await launch();
  let bad = 0;
  for (const w of [390, 1280]) {
    const { ctx, page, errors } = await open(browser, 'fx-lab', w);
    await page.click('[data-selftest]');
    await page.waitForFunction(() => { const r = document.querySelector('[data-report]'); return r && !r.hidden && /通过|失败|✓|✗/.test(r.textContent) && !/运行中/.test(r.textContent); }, null, { timeout: 60000 });
    await page.waitForTimeout(500);
    const text = await page.$eval('[data-report]', (el) => el.innerText);
    const fails = (text.match(/✗/g) || []).length;
    console.log(`--- fx-lab@${w}\n${text}`);
    if (fails || errors.length) { bad++; console.log('ERRORS', errors, 'fails', fails); }
    await ctx.close();
  }
  await browser.close();
  console.log(bad ? 'SELFTEST: problems found' : 'SELFTEST: all passed');
  process.exit(bad ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
