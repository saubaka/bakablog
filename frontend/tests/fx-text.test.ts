import { describe, expect, it } from 'vitest'
import { canSplit, graphemes, plain, splitLimit, words, WRAP_MAX } from '@/fx/text'

const joined = (s: string) => words(s).map((t) => t.t).join('')

describe('heading text', () => {
  it('keeps every character: no word list loses or duplicates text', () => {
    for (const s of ['我是 sau_baka，不是笨蛋！！', 'SQLite 备份：我差点把自己的数据弄丢', '（括号）里的字', 'a  b', '周末的云', '“引号”和——破折号…']) {
      expect(joined(s).replace(/\s+/g, ' ')).toBe(s.replace(/\s+/g, ' '))
    }
  })

  it('closing punctuation sticks to the word before it, opening punctuation to the word after it', () => {
    const toks = words('不是笨蛋！！然后（括号）')
    for (const t of toks) {
      expect(/^[，。、！？；：）》」』”’…—]/.test(t.t)).toBe(false)     // no word starts with a closing mark
      expect(/[（《「『“‘]$/.test(t.t)).toBe(false)                     // no word ends with an opening mark
    }
  })

  it('splits into characters that join back to the word', () => {
    expect(graphemes('差点').join('')).toBe('差点')
    expect(graphemes('a🙂b').length).toBe(3)
    expect(graphemes('éx').length).toBe(2)           // a letter with a combining accent is one character
  })

  it('splits only short headings: 32 characters, 24 on a phone', () => {
    expect(splitLimit(false)).toBe(32)
    expect(splitLimit(true)).toBe(24)
    expect(canSplit('短标题', true)).toBe(true)
    expect(canSplit('一'.repeat(25), true)).toBe(false)
    expect(canSplit('一'.repeat(25), false)).toBe(true)
    expect(canSplit('', false)).toBe(false)
  })

  it('leaves long unbroken runs alone', () => {
    expect(WRAP_MAX).toBe(12)
  })

  it('plain collapses whitespace', () => {
    expect(plain('  a \n b  ')).toBe('a b')
  })
})
