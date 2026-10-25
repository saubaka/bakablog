// In-page scans shared by the public and the admin audits (they run inside the page: Playwright sends their source).
export const scanLines = (floatingSel) => {
  const out = { shadow: [], border: [], square: [] }
  const rgb = (c) => (c.match(/[\d.]+/g) || []).map(Number)
  const near = (a, b) => a.length >= 3 && b.length >= 3 && Math.abs(a[0] - b[0]) < 2 && Math.abs(a[1] - b[1]) < 2 && Math.abs(a[2] - b[2]) < 2
  const probe = document.createElement('i'); document.body.append(probe)
  const token = (v) => { probe.style.color = `var(${v})`; return rgb(getComputedStyle(probe).color) }
  const LINE = token('--line'); const ROSE = token('--rose-line'); const PAPER = token('--paper')
  probe.remove()
  const label = (e) => `${e.tagName.toLowerCase()}.${String(e.className && e.className.baseVal !== undefined ? e.className.baseVal : e.className).split(' ').filter(Boolean).slice(0, 2).join('.')}`
  const floating = (e) => !!e.closest(floatingSel)
  const seen = new Set()
  document.querySelectorAll('body *').forEach((e) => {
    const cs = getComputedStyle(e); if (cs.display === 'none' || cs.visibility === 'hidden') return
    const r = e.getBoundingClientRect(); if (r.width < 2 || r.height < 2) return
    if (cs.boxShadow !== 'none' && !floating(e)) {
      const grey = [...cs.boxShadow.matchAll(/rgba?\(([^)]+)\)/g)].some((m) => { const c = rgb(m[1]); return c[3] === undefined || c[3] > 0.02 })
      const k = `${label(e)}|${cs.boxShadow}`
      // inset shadows are the marker highlight under a heading, not a halo; the 5px --fill ring is the keyboard focus halo
      if (grey && !seen.has(k) && !/inset/.test(cs.boxShadow) && !/0px 0px 0px 5px/.test(cs.boxShadow)) { seen.add(k); out.shadow.push(`${label(e)} :: ${cs.boxShadow.slice(0, 60)}`) }
    }
    ;['', '::before', '::after'].forEach((pe) => {
      const s = pe ? getComputedStyle(e, pe) : cs
      if (pe && (s.content === 'none' || s.content === 'normal')) return
      ;['Top', 'Right', 'Bottom', 'Left'].forEach((side) => {
        if (!(parseFloat(s[`border${side}Width`]) > 0) || s[`border${side}Style`] === 'none') return
        const c = rgb(s[`border${side}Color`]); if (c.length > 3 && c[3] < 0.05) return
        if (near(c, LINE) || near(c, ROSE) || near(c, PAPER)) return
        const k = `${label(e)}${pe}|${s[`border${side}Color`]}`
        if (!seen.has(k)) { seen.add(k); out.border.push(`${label(e)}${pe} ${side.toLowerCase()} ${s[`border${side}Color`]}`) }
      })
    })
    // a visible box (>= 3 border sides) that is at least 80x40 must be rounded
    if (r.width >= 80 && r.height >= 40 && !/^(TR|TD|TH|TABLE|THEAD|TBODY|IMG|SVG|HTML|BODY|MAIN|IFRAME|INPUT|SELECT|TEXTAREA)$/i.test(e.tagName) && !(e instanceof SVGElement)) {
      const sides = ['Top', 'Right', 'Bottom', 'Left'].filter((sd) => parseFloat(cs[`border${sd}Width`]) > 0 && cs[`border${sd}Style`] !== 'none').length
      const rad = Math.max(...['TopLeft', 'TopRight', 'BottomRight', 'BottomLeft'].map((k) => parseFloat(cs[`border${k}Radius`]) || 0))
      if (sides >= 3 && rad < 6 && !e.closest('.tabs')) out.square.push(`${label(e)} ${Math.round(r.width)}x${Math.round(r.height)} r=${rad}`)
    }
  })
  return out
}


export const scanContrast = () => {
  const rgba = (c) => { const m = c.match(/[\d.]+/g).map(Number); return { r: m[0], g: m[1], b: m[2], a: m.length > 3 ? m[3] : 1 } }
  const lum = (c) => { const f = (v) => { const s = v / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4 }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b) }
  const over = (top, bottom) => ({ r: top.r * top.a + bottom.r * (1 - top.a), g: top.g * top.a + bottom.g * (1 - top.a), b: top.b * top.a + bottom.b * (1 - top.a), a: 1 })
  const bgOf = (el) => {
    const stack = []
    for (let e = el; e; e = e.parentElement) {
      const cs = getComputedStyle(e)
      if (cs.backgroundImage !== 'none' && !cs.backgroundImage.includes('gradient')) return null   // a picture or pattern: not measurable
      const c = rgba(cs.backgroundColor); if (c.a > 0) stack.push(c); if (c.a >= 1) break
    }
    let base = { r: 255, g: 255, b: 255, a: 1 }
    const page = rgba(getComputedStyle(document.body).backgroundColor); if (page.a > 0) base = page
    for (let i = stack.length - 1; i >= 0; i -= 1) base = over(stack[i], base)
    return base
  }
  const bad = new Map(); let n = 0
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
  const seen = new Set()
  for (let t = walker.nextNode(); t; t = walker.nextNode()) {
    if (!t.nodeValue.trim()) continue
    const el = t.parentElement; if (!el || seen.has(el) || el.closest('.sr-only, script, style, noscript, svg, .fx-debug-tag, [data-audit-skip]')) continue
    seen.add(el)
    const cs = getComputedStyle(el); const r = el.getBoundingClientRect()
    if (cs.visibility === 'hidden' || cs.display === 'none' || r.width < 1 || r.height < 1) continue
    const bg = bgOf(el); if (!bg) continue
    let fg = rgba(cs.color); fg = over(fg, bg)
    const [hi, lo] = [lum(fg), lum(bg)].sort((a, b) => b - a)
    const ratio = (hi + 0.05) / (lo + 0.05)
    const size = parseFloat(cs.fontSize); const bold = parseInt(cs.fontWeight, 10) >= 700
    const need = size >= 24 || (bold && size >= 18.66) ? 3 : 4.5
    n += 1
    if (ratio < need) {
      const key = `${cs.color} on ${cs.backgroundColor === 'rgba(0, 0, 0, 0)' ? 'inherited' : cs.backgroundColor} (${ratio.toFixed(2)}:1, need ${need})`
      const v = bad.get(key) || { c: 0, ex: `${el.tagName.toLowerCase()}.${String(el.className).split(' ')[0]} "${t.nodeValue.trim().slice(0, 18)}"` }; v.c += 1; bad.set(key, v)
    }
  }
  return { n, bad: [...bad.entries()] }
}

