// Title word grouping: words that were split into spans must still read as one line of text.
// - no .ph / .fx-w span may be an item of a flex or grid container (that pulls the words apart),
// - two neighbouring word spans that sit on the same line and are joined only by <wbr> must touch.
const { PAGES, launch, open } = require('./common');
// SELFTEST=1 switches the fix off (text stays directly inside flex / grid boxes) and the audit must then fail
const SELFTEST = Boolean(process.env.SELFTEST);
const breakCalm = (page) => page.route('**/js/fx.js', async (route) => {
  const r = await route.fetch();
  route.fulfill({ response: r, body: (await r.text()).replace('function calm(node) {', 'function calm(node) { return;') });
});
(async () => {
  const browser = await launch();
  let bad = 0; let checked = 0;
  for (const name of PAGES) {
    for (const w of [390, 768, 1280]) {
      for (const query of ['motion=off', 'motion=full']) {
        const { ctx, page } = await open(browser, name, w, { query, before: SELFTEST ? breakCalm : undefined });
        const res = await page.evaluate(() => {
          const out = []; let n = 0;
          document.querySelectorAll('.ph, .fx-w').forEach((el) => {
            n += 1;
            const d = getComputedStyle(el.parentElement).display;
            if (/flex|grid/.test(d)) out.push(`flex/grid item: "${el.textContent}" in <${el.parentElement.tagName.toLowerCase()} class="${el.parentElement.className}">`);
            const nx = el.nextSibling && el.nextSibling.tagName === 'WBR' ? el.nextSibling.nextSibling : null;
            if (nx && nx.nodeType === 1 && (nx.classList.contains('ph') || nx.classList.contains('fx-w'))) {
              const a = el.getBoundingClientRect(); const b = nx.getBoundingClientRect();
              if (Math.abs(a.top - b.top) < 3 && b.left - a.right > 2) out.push(`gap ${(b.left - a.right).toFixed(1)}px between "${el.textContent}" and "${nx.textContent}"`);
            }
          });
          return { out, n };
        });
        checked += res.n;
        if (res.out.length) { bad += res.out.length; console.log(`✗ ${name}@${w} ${query}:`); res.out.slice(0, 6).forEach((l) => console.log('   ' + l)); }
        await ctx.close();
      }
    }
  }
  await browser.close();
  if (SELFTEST) { console.log(bad ? `self-test ok: the audit catches the broken grouping (${bad} problems)` : 'SELF-TEST FAILED: the audit did not notice the broken grouping'); process.exit(bad ? 0 : 1); }
  console.log(bad ? `TEXT AUDIT: ${bad} problem(s)` : `TEXT AUDIT: all clean (${checked} word spans checked)`);
  process.exit(bad ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
