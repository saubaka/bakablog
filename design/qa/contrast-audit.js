// Rendered text contrast on every page, for every theme preset. Text under 24px (18.66px bold) needs 4.5:1, bigger text 3:1.
const { PAGES, launch, open } = require('./common');
const THEMES = ['default', 'sky', 'sakura', 'fog'];
const scan = () => {
  const rgba = (c) => { const m = c.match(/[\d.]+/g).map(Number); return { r: m[0], g: m[1], b: m[2], a: m.length > 3 ? m[3] : 1 }; };
  const lum = (c) => { const f = (v) => { const s = v / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const over = (top, bottom) => ({ r: top.r * top.a + bottom.r * (1 - top.a), g: top.g * top.a + bottom.g * (1 - top.a), b: top.b * top.a + bottom.b * (1 - top.a), a: 1 });
  const bgOf = (el) => {
    const stack = [];
    for (let e = el; e; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.backgroundImage !== 'none' && !cs.backgroundImage.includes('gradient')) return null;
      const c = rgba(cs.backgroundColor); if (c.a > 0) stack.push(c); if (c.a >= 1) break;
    }
    let base = { r: 255, g: 255, b: 255, a: 1 };
    const page = rgba(getComputedStyle(document.body).backgroundColor); if (page.a > 0) base = page;
    for (let i = stack.length - 1; i >= 0; i -= 1) base = over(stack[i], base);
    return base;
  };
  const bad = new Map(); let n = 0;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const seen = new Set();
  for (let t = walker.nextNode(); t; t = walker.nextNode()) {
    if (!t.nodeValue.trim()) continue;
    const el = t.parentElement; if (!el || seen.has(el) || el.closest('.sr-only, script, style, noscript, svg, .dpanel, .fx-debug-tag, [data-audit-skip]')) continue;
    seen.add(el);
    const cs = getComputedStyle(el); const r = el.getBoundingClientRect();
    if (cs.visibility === 'hidden' || cs.display === 'none' || r.width < 1 || r.height < 1) continue;
    const bg = bgOf(el); if (!bg) continue;
    let fg = rgba(cs.color); fg = over(fg, bg);
    const [hi, lo] = [lum(fg), lum(bg)].sort((a, b) => b - a);
    const ratio = (hi + 0.05) / (lo + 0.05);
    const size = parseFloat(cs.fontSize); const bold = parseInt(cs.fontWeight, 10) >= 700;
    const need = size >= 24 || (bold && size >= 18.66) ? 3 : 4.5;
    n += 1;
    if (ratio < need) {
      const key = `${cs.color} on ${cs.backgroundColor === 'rgba(0, 0, 0, 0)' ? 'inherited' : cs.backgroundColor} (${ratio.toFixed(2)}:1, need ${need})`;
      const v = bad.get(key) || { c: 0, ex: `${el.tagName.toLowerCase()}.${String(el.className).split(' ')[0]} "${t.nodeValue.trim().slice(0, 18)}"` }; v.c += 1; bad.set(key, v);
    }
  }
  return { n, bad: [...bad.entries()] };
};
(async () => {
  const browser = await launch(); let failures = 0;
  for (const theme of THEMES) {
    const agg = new Map(); let total = 0;
    for (const name of PAGES) {
      const { ctx, page } = await open(browser, name, 1280, { query: 'motion=off', settle: 200 });
      await page.evaluate((th) => { if (th === 'default') document.documentElement.removeAttribute('data-theme'); else document.documentElement.setAttribute('data-theme', th); }, theme);
      await page.waitForTimeout(120);
      const r = await page.evaluate(scan); total += r.n;
      r.bad.forEach(([k, v]) => { const a = agg.get(k) || { c: 0, ex: v.ex, pages: new Set() }; a.c += v.c; a.pages.add(name); agg.set(k, a); });
      await ctx.close();
    }
    console.log(`${agg.size ? '✗' : '✓'} theme ${theme}: ${total} text elements, ${agg.size} failing colour pairs`);
    for (const [k, v] of agg) { failures += 1; console.log(`    ${v.c}× ${k}  e.g. ${v.ex}  [${[...v.pages].slice(0, 4).join(', ')}]`); }
  }
  await browser.close(); process.exitCode = failures ? 1 : 0;
})();
