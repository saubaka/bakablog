import { describe, expect, it } from 'vitest'
import { afterSave } from '@/admin/editor/save-state'
import { lineDiff, withContext } from '@/admin/editor/linediff'
import { callout, codeFence, continueList, counts, diff, footnote, images, indent, link, table, toggleBlock, wrap, type Sel } from '@/admin/editor/textedit'

const sel = (value: string, start = value.length, end = start): Sel => ({ value, start, end })

describe('Markdown editor transformations', () => {
  it('wrap puts marks around the selection, or between the cursor with a placeholder', () => {
    expect(wrap(sel('a word here', 2, 6), '**')).toEqual({ value: 'a **word** here', start: 4, end: 8 })
    expect(wrap(sel('ab', 1), '**', '**', '粗体')).toEqual({ value: 'a**粗体**b', start: 3, end: 5 })
  })
  it('wrapping twice undoes it, from the inside or the outside', () => {
    const once = wrap(sel('a word here', 2, 6), '**')
    expect(wrap(once, '**').value).toBe('a word here')
    expect(wrap(sel('a **word** here', 4, 8), '**').value).toBe('a word here')
  })

  it('toggleBlock makes lines a list and takes them back out again', () => {
    const list = toggleBlock(sel('one\ntwo', 0, 7), 'bullet')
    expect(list.value).toBe('- one\n- two')
    expect(toggleBlock({ ...list, start: 0, end: list.value.length }, 'bullet').value).toBe('one\ntwo')
    expect(toggleBlock(sel('a\nb', 0, 3), 'ordered').value).toBe('1. a\n2. b')
    expect(toggleBlock(sel('plain', 0, 0), 'task').value).toBe('- [ ] plain')
    expect(toggleBlock(sel('- x', 0, 0), 'quote').value).toBe('> x')               // a list item turns into a quote, the old marker goes
    expect(toggleBlock(sel('title', 0, 0), 'h2').value).toBe('## title')
  })

  it('Enter in a list continues it; an empty item leaves it', () => {
    expect(continueList(sel('- one'))?.value).toBe('- one\n- ')
    expect(continueList(sel('3. three'))?.value).toBe('3. three\n4. ')
    expect(continueList(sel('- [x] done'))?.value).toBe('- [x] done\n- [ ] ')
    expect(continueList(sel('> quote'))?.value).toBe('> quote\n> ')
    expect(continueList(sel('- one\n- '))?.value).toBe('- one\n')
    expect(continueList(sel('plain text'))).toBeNull()
    expect(continueList(sel('- one', 1, 3))).toBeNull()
  })

  it('Tab indents and Shift+Tab outdents the selected lines by two spaces', () => {
    expect(indent(sel('a\nb', 0, 3), false).value).toBe('  a\n  b')
    expect(indent(sel('  a\n  b', 0, 7), true).value).toBe('a\nb')
    expect(indent(sel('a', 0), true).value).toBe('a')
  })

  it('blocks are separated from their neighbours by blank lines', () => {
    expect(codeFence(sel('text'), 'ts').value).toBe('text\n\n```ts\n\n```')
    expect(codeFence(sel('before after', 6), 'ts').value).toMatch(/^before\n\n```ts\n\n```\n\n ?after$/)
    expect(callout(sel(''), 'tip').value).toContain(':::tip')
    expect(table(sel('x')).value).toMatch(/\| .* \|/)
    expect(link(sel('see here', 4, 8), 'https://example.com/').value).toBe('see [here](https://example.com/)')
  })

  it('footnotes number themselves after the highest existing one', () => {
    const first = footnote(sel('text'))
    expect(first.value).toContain('text[^1]')
    expect(first.value).toContain('[^1]: ')
    expect(footnote(sel('x[^1] y[^4]')).value).toContain('[^5]: ')
  })

  it('one picture is a figure, several are a gallery; brackets in the alt text cannot break the syntax', () => {
    expect(images(sel(''), [{ id: 7, alt: '云[1]' }]).value).toBe('![云1](media:7)')
    expect(images(sel(''), [{ id: 1, alt: 'a' }, { id: 2, alt: 'b' }]).value).toBe('![a](media:1)\n![b](media:2)')
    expect(images(sel(''), [{ id: 7, alt: 'p' }], true).value).toBe('![p](media:7){.polaroid}')
  })

  it('diff finds the smallest replaced range (so the textarea keeps its undo history)', () => {
    expect(diff('hello world', 'hello brave world')).toEqual({ from: 6, to: 6, inserted: 'brave ' })
    expect(diff('abc', 'abc')).toEqual({ from: 3, to: 3, inserted: '' })
    expect(diff('abcdef', 'abXef')).toEqual({ from: 2, to: 4, inserted: 'X' })
  })
  it('counts ignores whitespace for characters', () => {
    expect(counts('a b\nc')).toEqual({ chars: 3, lines: 2 })
    expect(counts('')).toEqual({ chars: 0, lines: 0 })
  })
})

describe('version history diff', () => {
  it('marks added and deleted lines and keeps the rest', () => {
    const d = lineDiff('a\nb\nc', 'a\nB\nc\nd')
    expect(d?.map((l) => `${l.kind}:${l.text}`)).toEqual(['same:a', 'del:b', 'add:B', 'same:c', 'add:d'])
  })
  it('identical texts have no change; a huge text is refused instead of freezing the page', () => {
    expect(lineDiff('x\ny', 'x\ny')?.every((l) => l.kind === 'same')).toBe(true)
    const big = Array.from({ length: 3100 }, (_, i) => String(i)).join('\n')
    expect(lineDiff(big, `${big}\nmore`)).toBeNull()
  })
  it('long unchanged stretches collapse into a gap with a little context around each change', () => {
    const a = Array.from({ length: 20 }, (_, i) => `l${i}`).join('\n')
    const b = a.replace('l10', 'CHANGED')
    const out = withContext(lineDiff(a, b) ?? [], 2)
    const gaps = out.filter((l) => l.kind === 'gap')
    expect(gaps).toHaveLength(2)
    expect(out.some((l) => l.kind === 'add')).toBe(true)
    expect(out.length).toBeLessThan(15)
  })
})


describe('saving while editing', () => {
  it('keeps newer text and nested selections while accepting canonical values for unchanged fields', () => {
    const submitted = { title: 'sent', content: 'old', tags: ['one'], cover: { id: 1 }, slug: '' }
    const current = { title: 'typing', content: 'old', tags: ['one', 'two'], cover: { id: 2 }, slug: '' }
    const response = { ...submitted, title: 'Sent', slug: 'sent', tags: ['one'] }
    expect(afterSave(current, submitted, response)).toEqual({ ...current, slug: 'sent' })
    expect(response.title).toBe('Sent')
  })
  it('takes canonical server values when nothing changed after submission', () => {
    const sent = { title: ' title ', tags: ['tag'] }
    expect(afterSave(sent, sent, { title: 'title', tags: ['Tag'] })).toEqual({ title: 'title', tags: ['Tag'] })
  })
})
