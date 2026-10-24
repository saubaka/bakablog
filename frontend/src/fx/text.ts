/* Words, characters and line-break rules for headings.
   Chinese can be broken anywhere by the browser, which splits words like 差|点. The browser's own dictionary segmenter
   (Intl.Segmenter) finds the words; they are kept together (nowrap) and lines break only between words. Closing
   punctuation sticks to the word before it, opening punctuation to the word after it, so no line starts with ，。！ . */

export interface Token { t: string; space: boolean }

const seg = (granularity: 'grapheme' | 'word') =>
  typeof Intl !== 'undefined' && 'Segmenter' in Intl ? new Intl.Segmenter('zh', { granularity }) : null
const graphemeSeg = seg('grapheme')
const wordSeg = seg('word')

const CLOSING = /^[，。、！？；：）》」』”’…—,.!?;:)\]}]+$/   // must not start a line
const OPENING = /^[（《「『“‘([{]+$/                          // must not end a line
/** Longer unbroken runs (URLs, long words) are left alone. */
export const WRAP_MAX = 12

export function graphemes(s: string): string[] {
  return graphemeSeg ? [...graphemeSeg.segment(s)].map((x) => x.segment) : Array.from(s)
}

export function words(text: string): Token[] {
  // no segmenter: Latin words and spaces only, Chinese breaks as before
  const raw = wordSeg ? [...wordSeg.segment(text)].map((x) => x.segment) : text.split(/(\s+)/).filter(Boolean)
  const out: Token[] = []
  for (const g of raw) {
    if (/^\s+$/.test(g)) { out.push({ t: ' ', space: true }); continue }
    const prev = out[out.length - 1]
    if (prev && !prev.space && CLOSING.test(g)) { prev.t += g; continue }
    out.push({ t: g, space: false })
  }
  for (let i = out.length - 2; i >= 0; i -= 1) {
    const cur = out[i]
    const next = out[i + 1]
    if (cur && next && !cur.space && OPENING.test(cur.t) && !next.space) { next.t = cur.t + next.t; out.splice(i, 1) }
  }
  return out
}

/** Headings longer than this stay whole (and fade as one block): 24 characters on a phone, 32 elsewhere. */
export function splitLimit(narrow: boolean): number {
  return narrow ? 24 : 32
}

export function canSplit(label: string, narrow: boolean): boolean {
  return label.length > 0 && label.length <= splitLimit(narrow)
}

export function plain(text: string): string {
  return text.replace(/\s+/g, ' ').trim()
}
