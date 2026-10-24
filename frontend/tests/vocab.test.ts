import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { DOODLES, ICONS } from '@/public/icons'

/* The server's vocabularies (backend/app/defaults.py) are the single source of names: every icon, doodle and mood it can send must have
   a drawing in the sprite, and the front end may only ask for drawings that exist. */
const sprite = readFileSync(join(process.cwd(), 'src/ui/sprite.svg'), 'utf8')
const defaults = readFileSync(join(process.cwd(), '../backend/app/defaults.py'), 'utf8')
const ids = new Set([...sprite.matchAll(/<symbol id="([^"]+)"/g)].map((m) => m[1]))

function pyTuple(name: string): string[] {
  const m = new RegExp(`${name}\\s*=\\s*\\(([^)]*)\\)`, 's').exec(defaults)
  return m ? [...(m[1] ?? '').matchAll(/"([^"]+)"/g)].map((x) => x[1] as string) : []
}
const moods = [...(/MOODS = \{([^}]*)\}/s.exec(defaults)?.[1] ?? '').matchAll(/"([a-z]+)":/g)].map((m) => m[1] as string)

describe('sprite vocabulary', () => {
  it('has a drawing for every icon the server can send', () => {
    const serverIcons = pyTuple('ICONS')
    expect(serverIcons.length).toBeGreaterThan(20)
    for (const n of serverIcons) expect(ids.has(`i-${n}`), `icon ${n}`).toBe(true)
  })
  it('has a drawing for every doodle and mood', () => {
    const serverDoodles = pyTuple('DOODLES')
    expect(serverDoodles).toEqual([...DOODLES])
    for (const n of serverDoodles) expect(ids.has(`d-${n}`), `doodle ${n}`).toBe(true)
    expect(moods.length).toBe(10)
    for (const n of moods) expect(ids.has(`mood-${n}`), `mood ${n}`).toBe(true)
  })
  it('the cloud (mascot, doodle) is gone from the sprite and from the vocabularies', () => {
    expect([...ids].filter((i) => /^m-/.test(i ?? '') || i === 'd-cloud')).toEqual([])
    expect(DOODLES).not.toContain('cloud' as never)
    expect(pyTuple('DOODLES')).not.toContain('cloud')
  })
  it('the front end icon list is exactly the sprite icon list', () => {
    const drawn = [...ids].filter((i) => (i ?? '').startsWith('i-')).map((i) => (i as string).slice(2)).sort()
    expect([...ICONS].sort()).toEqual(drawn)
  })
  it('the sprite itself carries no inline style attribute (CSP)', () => {
    expect(sprite).not.toMatch(/\sstyle=/)
  })
})
