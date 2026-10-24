import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { applyAppearance } from '@/public/appearance'
import { readMode } from '@/fx/engine'
import site from '@samples/site.json'
import type { SiteInfo } from '@/shared/types'

/* boot.js runs before the first paint as a plain script; the app repeats its decisions in TypeScript. They must never disagree. */
const bootSource = readFileSync(join(process.cwd(), 'src/public/boot.js'), 'utf8')
const base = site as unknown as SiteInfo

function runBoot(info: Partial<SiteInfo> | null, opts: { search?: string; stored?: string | null; reduce?: boolean } = {}): HTMLElement {
  document.head.innerHTML = ''
  document.body.innerHTML = ''
  const root = document.documentElement
  root.className = ''
  root.removeAttribute('data-theme'); root.removeAttribute('data-code-theme'); root.removeAttribute('data-fx-mode')
  if (info) {
    const el = document.createElement('script')
    el.id = 'bb-data'
    el.type = 'application/json'
    el.textContent = JSON.stringify({ path: '/', kind: 'home', status: 200, site: { ...base, ...info }, data: {} })
    document.body.append(el)
  }
  window.history.replaceState(null, '', `/${opts.search ?? ''}`)
  if (opts.stored) localStorage.setItem('bb:motion', opts.stored); else localStorage.removeItem('bb:motion')
  vi.stubGlobal('matchMedia', (q: string) => ({ matches: !!opts.reduce && q.includes('reduce'), addEventListener() {}, removeEventListener() {} }))
  new Function(bootSource)()
  return root
}

beforeEach(() => { vi.useFakeTimers() })
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); localStorage.clear() })

describe('boot.js', () => {
  it('sets theme, code theme and decor from the first-screen data', () => {
    const root = runBoot({ theme: 'sakura', code_theme: 'blossom', decor: { tape: false, doodles: true } })
    expect(root.getAttribute('data-theme')).toBe('sakura')
    expect(root.getAttribute('data-code-theme')).toBe('blossom')
    expect(root.classList.contains('no-tape')).toBe(true)
    expect(root.classList.contains('no-doodles')).toBe(false)
  })

  it('the default theme sets no attribute (the tokens are the default)', () => {
    expect(runBoot({ theme: 'default' }).hasAttribute('data-theme')).toBe(false)
  })

  it('guards: boot hides the server copy, fx-pending hides the animated elements; a timer lifts both', () => {
    const root = runBoot({ motion: 'full' })
    expect(root.classList.contains('boot')).toBe(true)
    expect(root.classList.contains('fx-pending')).toBe(true)
    vi.advanceTimersByTime(2700)
    expect(root.classList.contains('boot')).toBe(false)
    expect(root.classList.contains('fx-pending')).toBe(false)
  })

  it('without first-screen data it still works (dev server)', () => {
    const root = runBoot(null)
    expect(root.getAttribute('data-fx-mode')).toBe('full')
  })

  it('with motion off nothing is hidden waiting for the engine', () => {
    const root = runBoot({ motion: 'off' })
    expect(root.classList.contains('fx-off')).toBe(true)
    expect(root.classList.contains('fx-pending')).toBe(false)
  })

  // the motion level: boot.js and engine.readMode must agree in every combination
  const cases: { name: string; site: SiteInfo['motion']; search?: string; stored?: string | null; reduce?: boolean; expect: string }[] = [
    { name: 'site default', site: 'soft', expect: 'soft' },
    { name: 'visitor choice beats site default', site: 'soft', stored: 'full', expect: 'full' },
    { name: '?motion= beats the visitor choice', site: 'full', stored: 'full', search: '?motion=off', expect: 'off' },
    { name: 'system reduce-motion beats everything', site: 'full', stored: 'full', search: '?motion=full', reduce: true, expect: 'off' },
    { name: 'junk in storage falls back to the site default', site: 'soft', stored: 'turbo', expect: 'soft' },
    { name: 'junk in the address falls back', site: 'full', search: '?motion=wild', expect: 'full' },
  ]
  it.each(cases)('motion level: $name', (c) => {
    const root = runBoot({ motion: c.site }, { search: c.search, stored: c.stored, reduce: c.reduce })
    expect(root.getAttribute('data-fx-mode')).toBe(c.expect)
    expect(readMode(c.site)).toBe(c.expect)      // same inputs are still in place: location, storage, matchMedia
  })
})

describe('applyAppearance (the app-side twin)', () => {
  it('produces the same <html> state as boot.js for the same settings', () => {
    const info: Partial<SiteInfo> = { theme: 'fog', code_theme: 'fog', decor: { tape: true, doodles: false } }
    const fromBoot = runBoot(info)
    const a = [fromBoot.getAttribute('data-theme'), fromBoot.getAttribute('data-code-theme'), ['no-tape', 'no-doodles'].map((c) => fromBoot.classList.contains(c))]
    document.documentElement.className = ''
    document.documentElement.removeAttribute('data-theme'); document.documentElement.removeAttribute('data-code-theme')
    applyAppearance({ ...base, ...info } as SiteInfo)
    const r = document.documentElement
    const b = [r.getAttribute('data-theme'), r.getAttribute('data-code-theme'), ['no-tape', 'no-doodles'].map((c) => r.classList.contains(c))]
    expect(b).toEqual(a)
  })
})
