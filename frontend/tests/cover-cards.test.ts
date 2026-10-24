import { describe, expect, it } from 'vitest'
import { coverClasses, hash } from '@/shared/cover'
import { layoutFor, planGrid, rowSizes } from '@/public/cards'
import type { PostCard } from '@/shared/types'

const post = (patch: Partial<PostCard> = {}): PostCard => ({
  id: 1, slug: 'a', url: '/blog/a', title: 'A', summary: '', cover: null, cover_alt: '', cover_focus: { x: 0.5, y: 0.5 }, category: null, tags: [],
  series: null, pinned: false, featured: false, card_style: 'auto', published_at: '2026-10-18T00:00:00Z', updated_at: '2026-10-18T00:00:00Z', reading_minutes: 1, word_count: 100, ...patch,
})

describe('generated covers', () => {
  it('the same title always gets the same cover; different titles spread over the patterns', () => {
    expect(coverClasses('SQLite 备份')).toBe(coverClasses('SQLite 备份'))
    const seen = new Set(Array.from({ length: 80 }, (_, i) => coverClasses(`文章 ${i}`)))
    expect(seen.size).toBeGreaterThan(12)
    for (const c of seen) expect(c).toMatch(/^cv-(sky|rose|mist|paper) cv-(dots|stripe|grid|wave)$/)
  })
  it('hash is stable', () => {
    expect(hash('abc')).toBe(hash('abc'))
    expect(hash('abc')).not.toBe(hash('abd'))
  })
})

describe('card grid plan', () => {
  it('nine cards fill five whole rows on a wide screen: 1 · 2 · 3 · 2 · 1', () => {
    expect(rowSizes(9, 'mixed')).toEqual([1, 2, 3, 2, 1])
  })
  it('an incomplete last row is made of fewer, wider cards (never one half-width card)', () => {
    for (let n = 1; n <= 30; n += 1) {
      for (const cols of [1, 2, 3] as const) for (const mode of ['mixed', 'grid'] as const) {
        const rows = rowSizes(n, mode, cols)
        expect(rows.reduce((a, b) => a + b, 0)).toBe(n)
        const last = rows[rows.length - 1] as number
        const plan = planGrid(Array.from({ length: n }, (_, i) => post({ id: i })), mode, cols)
        expect(plan).toHaveLength(n)
        // spans of the last row add up to a full row (6 columns)
        const lastSpans = plan.slice(n - last).map((s) => s.span)
        expect(lastSpans.reduce((a, b) => a + b, 0)).toBe(6)
      }
    }
  })
  it('two columns: a wide card first, then pairs', () => {
    expect(rowSizes(9, 'mixed', 2)).toEqual([1, 2, 2, 2, 2])
    expect(rowSizes(5, 'grid', 2)).toEqual([2, 2, 1])
  })
  it('layouts: wide = side, explicit style wins, a row of three alternates note / quote / picture', () => {
    expect(layoutFor(post(), 6)).toBe('side')
    expect(layoutFor(post({ card_style: 'quote' }), 3)).toBe('quote')
    expect(layoutFor(post({ card_style: 'side' }), 3)).toBe('cover')
    expect([0, 1, 2].map((c) => layoutFor(post(), 2, c))).toEqual(['note', 'quote', 'short'])
    expect(layoutFor(post({ cover: { id: 1 } as never }), 2, 0)).toBe('short')
  })
})
