import type { PostCard } from '@/shared/types'

/* Which card goes where. The grid has six columns; a card spans 6 (a wide card lying across the row), 3 (two per row) or 2 (three per row).
   "mixed" repeats 1 · 2 · 3 · 2 cards per row, so nine posts fill five whole rows; "grid" is three per row. A last row that cannot be
   completed gets a shape that fills it, so no card is ever left alone at half width. */

export type CardLayout = 'side' | 'cover' | 'note' | 'quote' | 'short' | 'mini'
export type Span = 2 | 3 | 6
export interface Slot { span: Span; layout: CardLayout }

const MIXED_ROWS: number[] = [1, 2, 3, 2]
const SPAN_OF_ROW: Record<number, Span> = { 1: 6, 2: 3, 3: 2 }

/** How many cards go in each row. Wide: 1 · 2 · 3 · 2 repeating ("mixed") or 3 per row ("grid"). Two columns (tablet): a wide first card,
    then pairs ("mixed") or only pairs ("grid"). One column (phone): the wide plan, every card gets its own row anyway.
    In every plan a last row that cannot be completed is made of fewer, wider cards, so no card is left alone at half width. */
export function rowSizes(count: number, mode: 'mixed' | 'grid', cols: 1 | 2 | 3 = 3): number[] {
  const rows: number[] = []
  let left = count
  for (let i = 0; left > 0; i += 1) {
    let want: number
    if (cols === 2) want = mode === 'mixed' && i === 0 ? 1 : 2
    else want = mode === 'grid' ? 3 : (MIXED_ROWS[i % MIXED_ROWS.length] as number)
    const take = Math.min(want, left)
    rows.push(take)
    left -= take
  }
  return rows
}

/** Layout of one card. An explicit card_style of the post wins; "auto" depends on how wide the card is, whether it has a picture and
    which column of its row it sits in (a row of three alternates note · quote · picture, so the row never looks like three copies). */
export function layoutFor(post: PostCard, span: Span, col = 0): CardLayout {
  switch (post.card_style) {
    case 'side': return span === 6 ? 'side' : 'cover'
    case 'cover': return 'cover'
    case 'note': return 'note'
    case 'quote': return 'quote'
    default: break
  }
  if (span === 6) return 'side'
  if (span === 3) return 'cover'
  if (post.cover) return 'short'
  return col === 1 ? 'quote' : col === 0 ? 'note' : 'short'
}

export function planGrid(posts: PostCard[], mode: 'mixed' | 'grid', cols: 1 | 2 | 3 = 3): Slot[] {
  const out: Slot[] = []
  let at = 0
  for (const size of rowSizes(posts.length, mode, cols)) {
    const span = SPAN_OF_ROW[size] as Span
    for (let i = 0; i < size; i += 1) {
      const post = posts[at]
      at += 1
      if (post) out.push({ span, layout: mode === 'grid' && span === 2 && post.card_style === 'auto' ? 'cover' : layoutFor(post, span, i) })
    }
  }
  return out
}
