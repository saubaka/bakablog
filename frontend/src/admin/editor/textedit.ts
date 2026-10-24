/* Text transformations of the Markdown editor, as pure functions on { value, start, end } (a selection in a string).
   The component applies the result to the <textarea> in a way that keeps the browser's own undo history. */

export interface Sel { value: string; start: number; end: number }

const lineStart = (v: string, i: number): number => v.lastIndexOf('\n', i - 1) + 1
const lineEnd = (v: string, i: number): number => { const k = v.indexOf('\n', i); return k < 0 ? v.length : k }

/** **bold**: wrap the selection; with nothing selected, put the cursor between the marks. Wrapping an already wrapped selection unwraps it. */
export function wrap(s: Sel, before: string, after = before, placeholder = ''): Sel {
  const { value, start, end } = s
  const picked = value.slice(start, end)
  if (picked.startsWith(before) && picked.endsWith(after) && picked.length >= before.length + after.length) {
    const inner = picked.slice(before.length, picked.length - after.length)
    return { value: value.slice(0, start) + inner + value.slice(end), start, end: start + inner.length }
  }
  if (value.slice(start - before.length, start) === before && value.slice(end, end + after.length) === after && start >= before.length) {
    return { value: value.slice(0, start - before.length) + picked + value.slice(end + after.length), start: start - before.length, end: end - before.length }
  }
  const text = picked || placeholder
  const next = value.slice(0, start) + before + text + after + value.slice(end)
  return { value: next, start: start + before.length, end: start + before.length + text.length }
}

/** The lines touched by the selection, as [from, to) offsets. */
function lineRange(s: Sel): [number, number] {
  const from = lineStart(s.value, s.start)
  const to = lineEnd(s.value, s.end > s.start && s.value[s.end - 1] === '\n' ? s.end - 1 : s.end)
  return [from, to]
}

const BULLET = /^(\s*)([-*+])\s+(?!\[[ xX]\])/
const TASK = /^(\s*)[-*+]\s+\[[ xX]\]\s+/
const ORDERED = /^(\s*)(\d+)[.)]\s+/
const QUOTE = /^(\s*)>\s?/
const HEADING = /^(#{1,6})\s+/

/** Turn the selected lines into a list / quote / heading, or back into plain lines when they already are one. */
export function toggleBlock(s: Sel, kind: 'quote' | 'bullet' | 'ordered' | 'task' | 'h2' | 'h3' | 'h4'): Sel {
  const [from, to] = lineRange(s)
  const lines = s.value.slice(from, to).split('\n')
  const test = { quote: QUOTE, bullet: BULLET, ordered: ORDERED, task: TASK, h2: /^##\s+(?!#)/, h3: /^###\s+(?!#)/, h4: /^####\s+(?!#)/ }[kind]
  const all = lines.every((l) => !l.trim() || test.test(l))
  const strip = (l: string): string => l.replace(TASK, '$1').replace(BULLET, '$1').replace(ORDERED, '$1').replace(QUOTE, '$1').replace(HEADING, '')
  let n = 0
  const out = lines.map((l) => {
    if (!l.trim()) return l
    if (all) return strip(l)
    const plain = strip(l)
    n += 1
    switch (kind) {
      case 'quote': return `> ${plain}`
      case 'bullet': return `- ${plain}`
      case 'task': return `- [ ] ${plain}`
      case 'ordered': return `${n}. ${plain}`
      default: return `${'#'.repeat(Number(kind[1]))} ${plain}`
    }
  })
  const text = out.join('\n')
  return { value: s.value.slice(0, from) + text + s.value.slice(to), start: from, end: from + text.length }
}

/** Put a block (code fence, table, callout ...) on its own lines with a blank line before and after. */
export function insertBlock(s: Sel, block: string, selectInner?: [number, number]): Sel {
  const { value, start, end } = s
  const before = value.slice(0, start)
  const after = value.slice(end)
  const pre = before === '' || before.endsWith('\n\n') ? '' : before.endsWith('\n') ? '\n' : '\n\n'
  const post = after === '' || after.startsWith('\n\n') ? '' : after.startsWith('\n') ? '\n' : '\n\n'
  const at = before.length + pre.length
  const next = before + pre + block + post + after
  return selectInner ? { value: next, start: at + selectInner[0], end: at + selectInner[1] } : { value: next, start: at + block.length, end: at + block.length }
}

export function link(s: Sel, url: string): Sel {
  const picked = s.value.slice(s.start, s.end) || '链接文字'
  const text = `[${picked}](${url})`
  return { value: s.value.slice(0, s.start) + text + s.value.slice(s.end), start: s.start + 1, end: s.start + 1 + picked.length }
}

export function codeFence(s: Sel, lang = ''): Sel {
  const picked = s.value.slice(s.start, s.end)
  const block = `\`\`\`${lang}\n${picked}\n\`\`\``
  return insertBlock(s, block, [4 + lang.length, 4 + lang.length + picked.length])
}

export function callout(s: Sel, kind: 'tip' | 'note' | 'warn' | 'love'): Sel {
  const picked = s.value.slice(s.start, s.end) || '写在这里'
  const block = `:::${kind}\n${picked}\n:::`
  return insertBlock(s, block, [4 + kind.length, 4 + kind.length + picked.length])
}

export function table(s: Sel): Sel {
  const block = '| 列一 | 列二 | 列三 |\n| --- | --- | --- |\n| 内容 | 内容 | 内容 |\n| 内容 | 内容 | 内容 |'
  return insertBlock(s, block, [2, 4])
}

export const rule = (s: Sel): Sel => insertBlock(s, '---')

export function footnote(s: Sel): Sel {
  const labels = [...s.value.matchAll(/\[\^(\d+)\]/g)].map((m) => Number(m[1]))
  const n = (labels.length ? Math.max(...labels) : 0) + 1
  const marked = `${s.value.slice(0, s.end)}[^${n}]${s.value.slice(s.end)}`
  const tail = `${marked.endsWith('\n') ? '' : '\n'}\n[^${n}]: 注释内容`
  const value = marked + tail
  return { value, start: value.length - 4, end: value.length }
}

/** Images: one picture is a figure, several in a row become a gallery (the server decides, see docs/API.md section 6). */
export function images(s: Sel, items: { id: number; alt: string }[], polaroid = false): Sel {
  const refs = items.map((i) => `![${i.alt.replace(/[\][]/g, '')}](media:${i.id})${polaroid && items.length === 1 ? '{.polaroid}' : ''}`)
  const block = items.length > 1 ? refs.join('\n') : refs.join('')
  return insertBlock(s, block)
}

/** Enter inside a list continues it (an empty item ends it). Returns null when the line is not a list item. */
export function continueList(s: Sel): Sel | null {
  if (s.start !== s.end) return null
  const at = s.start
  const from = lineStart(s.value, at)
  const line = s.value.slice(from, at)
  const rest = s.value.slice(at, lineEnd(s.value, at))
  const m = /^(\s*)(?:([-*+])\s+(\[[ xX]\]\s+)?|(\d+)([.)])\s+|(>)\s?)/.exec(line)
  if (!m) return null
  const marker = m[0]
  if (line.trim() === marker.trim() && !rest) {      // an empty item: remove the marker, leave the list
    return { value: s.value.slice(0, from) + s.value.slice(at), start: from, end: from }
  }
  const indent = m[1] ?? ''
  let next: string
  if (m[4]) next = `${indent}${Number(m[4]) + 1}${m[5]} `
  else if (m[6]) next = `${indent}> `
  else next = `${indent}${m[2]} ${m[3] ? '[ ] ' : ''}`
  const insert = `\n${next}`
  return { value: s.value.slice(0, at) + insert + s.value.slice(at), start: at + insert.length, end: at + insert.length }
}

/** Tab / Shift+Tab: indent or outdent the selected lines by two spaces (four for code is the author's choice, not ours). */
export function indent(s: Sel, outdent: boolean): Sel {
  const [from, to] = lineRange(s)
  const lines = s.value.slice(from, to).split('\n')
  let delta = 0
  let first = 0
  const out = lines.map((l, i) => {
    if (outdent) {
      const m = /^( {1,2}|\t)/.exec(l)
      if (!m) return l
      if (i === 0) first = -m[0].length
      delta -= m[0].length
      return l.slice(m[0].length)
    }
    if (i === 0) first = 2
    delta += 2
    return `  ${l}`
  })
  const text = out.join('\n')
  const single = s.start === s.end
  return { value: s.value.slice(0, from) + text + s.value.slice(to), start: Math.max(from, s.start + first), end: single ? Math.max(from, s.end + first) : s.end + delta }
}

/** What changed between two strings: the smallest [from, to) range of `a` that was replaced by `inserted` to get `b`. */
export function diff(a: string, b: string): { from: number; to: number; inserted: string } {
  let from = 0
  const max = Math.min(a.length, b.length)
  while (from < max && a[from] === b[from]) from += 1
  let endA = a.length
  let endB = b.length
  while (endA > from && endB > from && a[endA - 1] === b[endB - 1]) { endA -= 1; endB -= 1 }
  return { from, to: endA, inserted: b.slice(from, endB) }
}

export function counts(text: string): { chars: number; lines: number } {
  const chars = [...text.replace(/\s+/g, '')].length
  return { chars, lines: text ? text.split('\n').length : 0 }
}
