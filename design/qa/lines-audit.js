// One line colour, flat cards, no square "cards", no grey halos. Floating layers may have a (blue) shadow.
const { PAGES, launch, open } = require('./common');
const scan = () => {
  const out = { shadow: [], border: [], square: [] };
  const rgb = (c) => (c.match(/[\d.]+/g) || []).map(Number);
  const near = (a, b) => a.length >= 3 && b.length >= 3 && Math.abs(a[0] - b[0]) < 2 && Math.abs(a[1] - b[1]) < 2 && Math.abs(a[2] - b[2]) < 2;
  const probe = document.createElement('i'); document.body.append(probe);
  const token = (v) => { probe.style.color = `var(${v})`; return rgb(getComputedStyle(probe).color); };
  const LINE = token('--line'); const ROSE = token('--rose-line'); const PAPER = token('--paper');
  probe.remove();
  const label = (e) => `${e.tagName.toLowerCase()}.${String(e.className && e.className.baseVal !== undefined ? e.className.baseVal : e.className).split(' ').filter(Boolean).slice(0, 2).join('.')}`;
  const floating = (e) => !!e.closest('.sheet, .toast, dialog, .dpanel__body, .tabbar, .lightbox, .scrim, .searchbox');
  const seen = new Set();
  document.querySelectorAll('body *').forEach((e) => {
    const cs = getComputedStyle(e); if (cs.display === 'none') return;
    const r = e.getBoundingClientRect(); if (r.width < 2 || r.height < 2) return;
    if (cs.boxShadow !== 'none' && !floating(e)) {
      const grey = [...cs.boxShadow.matchAll(/rgba?\(([^)]+)\)/g)].some((m) => { const c = rgb(m[1]); return c[3] === undefined || c[3] > 0.02; });
      const k = `${label(e)}|${cs.boxShadow}`;
      // the keyboard-focus halo is a 0-offset ring in --fill, not a shadow; it only exists while focused
      // inset shadows are the marker highlight under a heading, not a halo; the 5px --fill ring is the keyboard focus halo
      if (grey && !seen.has(k) && !/inset/.test(cs.boxShadow) && !/0px 0px 0px 5px/.test(cs.boxShadow)) { seen.add(k); out.shadow.push(`${label(e)} :: ${cs.boxShadow.slice(0, 60)}`); }
    }
    ['', '::before', '::after'].forEach((pe) => {
      const s = pe ? getComputedStyle(e, pe) : cs;
      if (pe && (s.content === 'none' || s.content === 'normal')) return;
      ['Top', 'Right', 'Bottom', 'Left'].forEach((side) => {
        if (!(parseFloat(s[`border${side}Width`]) > 0) || s[`border${side}Style`] === 'none') return;
        const c = rgb(s[`border${side}Color`]); if (c.length > 3 && c[3] < 0.05) return;
        if (near(c, LINE) || near(c, ROSE) || near(c, PAPER)) return;
        const k = `${label(e)}${pe}|${s[`border${side}Color`]}`;
        if (!seen.has(k)) { seen.add(k); out.border.push(`${label(e)}${pe} ${side.toLowerCase()} ${s[`border${side}Color`]}`); }
      });
    });
    // a visible box (>= 3 border sides, or a fill) that is at least 80x40 must be rounded
    if (r.width >= 80 && r.height >= 40 && !/^(TR|TD|TH|TABLE|THEAD|TBODY|IMG|SVG|HTML|BODY|MAIN|IFRAME|INPUT|SELECT|TEXTAREA)$/i.test(e.tagName) && !(e instanceof SVGElement)) {
      const sides = ['Top', 'Right', 'Bottom', 'Left'].filter((sd) => parseFloat(cs[`border${sd}Width`]) > 0 && cs[`border${sd}Style`] !== 'none').length;
      const rad = Math.max(...['TopLeft', 'TopRight', 'BottomRight', 'BottomLeft'].map((k) => parseFloat(cs[`border${k}Radius`]) || 0));
      if (sides >= 3 && rad < 6 && !e.closest('.site-header, .tabs')) out.square.push(`${label(e)} ${Math.round(r.width)}x${Math.round(r.height)} r=${rad}`);
    }
  });
  return out;
};
(async () => {
  const browser = await launch(); let bad = 0; const all = { shadow: new Map(), border: new Map(), square: new Map() };
  for (const name of PAGES) for (const w of [1280, 390]) {
    const { ctx, page } = await open(browser, name, w, { query: 'motion=off', settle: 300 });
    const r = await page.evaluate(scan);
    for (const k of Object.keys(all)) for (const line of r[k]) { const m = all[k].get(line) || new Set(); m.add(`${name}@${w}`); all[k].set(line, m); }
    await ctx.close();
  }
  for (const [k, title] of [['shadow', 'drop shadow on a non-floating element'], ['border', 'border colour that is not --line / --rose-line'], ['square', 'square "card"']]) {
    console.log(`${all[k].size ? '✗' : '✓'} ${title}: ${all[k].size}`);
    for (const [line, where] of all[k]) { bad += 1; console.log(`    ${line}  [${[...where].slice(0, 3).join(', ')}]`); }
  }
  await browser.close(); process.exitCode = bad ? 1 : 0;
})();
