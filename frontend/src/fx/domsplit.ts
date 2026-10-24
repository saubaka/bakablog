import { charOffset } from './math'
import { graphemes, plain, splitLimit, words } from './text'

/* Splitting a heading that Vue does not own: the h2 of an article arrives as server-made HTML (v-html), so unlike FxText
   it is split by changing the DOM once, right after the HTML is inserted. It is never patched by Vue afterwards
   (a new article replaces the whole container). Returns false when the heading is too long to split. */
export function splitHeading(el: HTMLElement, narrow: boolean): boolean {
  if (el.dataset.fxSplit) return true
  const label = plain(el.textContent ?? '')
  if (!label || label.length > splitLimit(narrow)) return false
  if (!el.hasAttribute('aria-label')) el.setAttribute('aria-label', label)
  const chars: HTMLElement[] = []
  const walk = (node: Node): void => {
    for (const child of [...node.childNodes]) {
      if (child.nodeType === Node.TEXT_NODE) {
        const frag = document.createDocumentFragment()
        const toks = words(child.nodeValue ?? '')
        toks.forEach((tk, i) => {
          if (tk.space) { frag.append(document.createTextNode(' ')); return }
          const w = document.createElement('span')
          w.className = 'fx-w'
          w.setAttribute('aria-hidden', 'true')
          for (const g of graphemes(tk.t)) {
            const c = document.createElement('span')
            c.className = 'fx-c'
            c.textContent = g
            chars.push(c)
            w.append(c)
          }
          frag.append(w)
          const next = toks[i + 1]
          if (next && !next.space) frag.append(document.createElement('wbr'))
        })
        child.replaceWith(frag)
      } else if (child.nodeType === Node.ELEMENT_NODE && (child as Element).tagName !== 'BR') {
        walk(child)
      }
    }
  }
  walk(el)
  chars.forEach((c, i) => c.style.setProperty('--co', String(charOffset(i, chars.length))))
  el.dataset.fxSplit = '1'
  return true
}
