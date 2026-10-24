/* A line-by-line comparison of two texts (version history). Classic longest-common-subsequence on lines; texts beyond a few thousand
   lines are reported as "too long to compare" instead of freezing the page. */
export interface DiffLine { kind: 'same' | 'add' | 'del'; text: string }

const LIMIT = 3000

export function lineDiff(a: string, b: string): DiffLine[] | null {
  const x = a.split('\n')
  const y = b.split('\n')
  if (x.length > LIMIT || y.length > LIMIT) return null
  // trim the common head and tail first: most edits touch a small part
  let head = 0
  while (head < x.length && head < y.length && x[head] === y[head]) head += 1
  let tail = 0
  while (tail < x.length - head && tail < y.length - head && x[x.length - 1 - tail] === y[y.length - 1 - tail]) tail += 1
  const mx = x.slice(head, x.length - tail)
  const my = y.slice(head, y.length - tail)
  const n = mx.length
  const m = my.length
  const table: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0))
  for (let i = n - 1; i >= 0; i -= 1) {
    for (let j = m - 1; j >= 0; j -= 1) {
      table[i]![j] = mx[i] === my[j] ? (table[i + 1]![j + 1] as number) + 1 : Math.max(table[i + 1]![j] as number, table[i]![j + 1] as number)
    }
  }
  const out: DiffLine[] = x.slice(0, head).map((text) => ({ kind: 'same', text }))
  let i = 0
  let j = 0
  while (i < n && j < m) {
    if (mx[i] === my[j]) { out.push({ kind: 'same', text: mx[i] as string }); i += 1; j += 1 }
    else if ((table[i + 1]![j] as number) >= (table[i]![j + 1] as number)) { out.push({ kind: 'del', text: mx[i] as string }); i += 1 }
    else { out.push({ kind: 'add', text: my[j] as string }); j += 1 }
  }
  while (i < n) { out.push({ kind: 'del', text: mx[i] as string }); i += 1 }
  while (j < m) { out.push({ kind: 'add', text: my[j] as string }); j += 1 }
  for (const text of x.slice(x.length - tail)) out.push({ kind: 'same', text })
  return out
}

/** Collapse long unchanged stretches so the diff shows the changes with a little context. */
export function withContext(lines: DiffLine[], context = 2): (DiffLine | { kind: 'gap'; count: number })[] {
  const keep = new Array<boolean>(lines.length).fill(false)
  lines.forEach((l, i) => {
    if (l.kind === 'same') return
    for (let k = Math.max(0, i - context); k <= Math.min(lines.length - 1, i + context); k += 1) keep[k] = true
  })
  const out: (DiffLine | { kind: 'gap'; count: number })[] = []
  let gap = 0
  lines.forEach((l, i) => {
    if (keep[i]) { if (gap) { out.push({ kind: 'gap', count: gap }); gap = 0 } out.push(l) } else gap += 1
  })
  if (gap) out.push({ kind: 'gap', count: gap })
  return out
}
