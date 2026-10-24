import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import postcss from 'postcss'
import { describe, expect, it } from 'vitest'

/* Hard rules of the project, checked on the sources so a change that breaks one fails before it ships. */
const root = `${join(process.cwd(), 'src')}/`
function walk(dir: string, out: string[] = []): string[] {
  for (const f of readdirSync(dir)) {
    const p = join(dir, f)
    if (statSync(p).isDirectory()) walk(p, out)
    else out.push(p)
  }
  return out
}
const files = walk(root)
const vue = files.filter((f) => f.endsWith('.vue'))
const css = files.filter((f) => f.endsWith('.css'))
const rel = (f: string) => f.slice(root.length)

describe('CSS discipline', () => {
  it('declares the one layer order first and keeps every rule inside a layer', () => {
    const tokens = postcss.parse(readFileSync(join(root, 'ui/css/tokens.css'), 'utf8'))
    const first = tokens.nodes.find((n) => n.type === 'atrule')
    expect(first && 'params' in first ? first.params : '').toBe('reset, tokens, base, components, layout, pages, fx, utilities')
    for (const f of css) {
      for (const node of postcss.parse(readFileSync(f, 'utf8')).nodes) {
        if (node.type === 'comment') continue
        const ok = node.type === 'atrule' && ['layer', 'font-face', 'import', 'keyframes'].includes(node.name)
        expect(ok, `${rel(f)}: unlayered ${node.type} ${'selector' in node ? node.selector : 'name' in node ? node.name : ''}`).toBe(true)
        // at-rule blocks other than @layer / @font-face / @keyframes would be unlayered rules in disguise
        if (node.type === 'atrule' && node.name === 'import') expect(['ui/css/index.css', 'admin/css/index.css'], `${rel(f)} imports`).toContain(rel(f))
      }
    }
  })

  it('imports every stylesheet in layer order', () => {
    const idx = readFileSync(join(root, 'ui/css/index.css'), 'utf8')
    const order = [...idx.matchAll(/@import '\.\/([a-z]+)\.css'/g)].map((m) => m[1])
    expect(order).toEqual(['tokens', 'base', 'components', 'layout', 'prose', 'pages', 'fx'])
  })

  it("the admin's stylesheet starts with the shared tokens, then base and components, and never pulls in the public page's layout or pages CSS", () => {
    const idx = readFileSync(join(root, 'admin/css/index.css'), 'utf8')
    const imports = [...idx.matchAll(/@import '([^']+)'/g)].map((m) => m[1])
    expect(imports.slice(0, 3)).toEqual(['../../ui/css/tokens.css', '../../ui/css/base.css', '../../ui/css/components.css'])
    expect(imports.filter((i) => /ui\/css\/(layout|pages)\.css/.test(i ?? ''))).toEqual([])
    expect(imports.slice(-3)).toEqual(['./shell.css', './kit.css', './pages.css'])
  })

  it('<main> never draws a focus ring', () => {
    const base = readFileSync(join(root, 'ui/css/base.css'), 'utf8')
    expect(base).toMatch(/main:focus[^{]*\{[^}]*outline:\s*none/s)
  })

  it('the only line colour is --line (+ the pink twin): no stray hex in borders', () => {
    const allowed = /var\(--(line|rose-line|paper|accent-line|ico-line|sky-\d+|ring)\)|transparent|none|currentColor/
    for (const f of css) {
      postcss.parse(readFileSync(f, 'utf8')).walkDecls(/^border(-(top|right|bottom|left))?(-color)?$/, (d) => {
        if (/^border(-(top|right|bottom|left))?$/.test(d.prop) && /^\s*(0|none)\b/.test(d.value)) return
        expect(allowed.test(d.value), `${rel(f)}: ${d.prop}: ${d.value}`).toBe(true)
      })
    }
  })

  it('no dark colours anywhere (the deepest tone is the ink, used for text only)', () => {
    for (const f of css) {
      const text = readFileSync(f, 'utf8')
      for (const m of text.matchAll(/#([0-9a-fA-F]{6})\b/g)) {
        const hex = m[1] as string
        const lum = (0.2126 * Number.parseInt(hex.slice(0, 2), 16) + 0.7152 * Number.parseInt(hex.slice(2, 4), 16) + 0.0722 * Number.parseInt(hex.slice(4), 16)) / 255
        // text and mask colours may be deep (ink, code tokens); backgrounds may not: only flag a *background* declaration
        const line = text.slice(text.lastIndexOf('\n', m.index) + 1, text.indexOf('\n', m.index))
        if (/background(-color)?\s*:/.test(line) && !/mask|%23/.test(line)) expect(lum, `${rel(f)}: ${line.trim()}`).toBeGreaterThan(0.55)
      }
    }
  })
})

describe('templates obey the CSP (script-src and style-src are "self")', () => {
  it('no literal style="" attribute and no inline event handler in any component', () => {
    for (const f of vue) {
      const tpl = /<template>[\s\S]*<\/template>/.exec(readFileSync(f, 'utf8'))?.[0] ?? ''
      expect(tpl, `${rel(f)} has a literal style attribute`).not.toMatch(/\sstyle="/)
      expect(tpl, `${rel(f)} has an inline handler`).not.toMatch(/\son[a-z]+="/)
    }
  })

  it('no <style> blocks (they would be unlayered CSS)', () => {
    for (const f of vue) expect(readFileSync(f, 'utf8'), rel(f)).not.toMatch(/<style[\s>]/)
  })

  it('v-html is used only where the HTML is sanitised by the server', () => {
    const users = vue.filter((f) => /v-html/.test(readFileSync(f, 'utf8'))).map(rel).sort()
    expect(users).toEqual([
      'admin/editor/PreviewPane.vue',       // the server's own Markdown preview of what is being written (same pipeline, same allow-list)
      'admin/pages/Moments.vue',            // moment.html as the admin API returns it
      'admin/ui/AdminSprite.vue',           // our own icon file
      'public/components/MomentView.vue',   // moment.html: Markdown pipeline, allow-list
      'public/components/ProseView.vue',    // post / page html: Markdown pipeline, allow-list
      'public/layout/SearchDialog.vue',     // snippets: escaped by the server, only <mark> survives
      'public/pages/Search.vue',            // snippets: same
      'ui/components/Sprite.vue',           // our own sprite file
    ])
  })

  it('the cloud mascot is gone: no component, class, flag or sprite symbol of it is left in the sources', () => {
    for (const f of files.filter((x) => /\.(ts|vue|js|css|svg)$/.test(x))) {
      expect(readFileSync(f, 'utf8'), rel(f)).not.toMatch(/mascot|\bm-(idle|happy|sleepy|think|body)\b|d-cloud|cv-cloud|hr-cloud/i)
    }
  })

  it('no eval, no Function constructor, no document.write, no innerHTML assignment', () => {
    for (const f of files.filter((x) => /\.(ts|vue|js)$/.test(x))) {
      const text = readFileSync(f, 'utf8')
      expect(text, rel(f)).not.toMatch(/\beval\(|new Function\(|document\.write\(|\.innerHTML\s*=/)
    }
  })

  it('nothing talks to another host', () => {
    for (const f of files.filter((x) => /\.(ts|vue|js|css)$/.test(x))) {
      const text = readFileSync(f, 'utf8').replace(/xmlns='http:\/\/www\.w3\.org\/2000\/svg'|xmlns="http:\/\/www\.w3\.org\/2000\/svg"/g, '')
      for (const m of text.matchAll(/https?:\/\/[^\s'"`)]+/g)) {
        expect(/^https?:\/\/(beian\.miit\.gov\.cn|localhost|127\.0\.0\.1)/.test(m[0]) || /^https?:\/\/(example\.com|x\.test|…)/.test(m[0]), `${rel(f)}: ${m[0]}`).toBe(true)
      }
    }
  })
})
