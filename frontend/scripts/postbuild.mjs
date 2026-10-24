/* After `vite build`: turn dist/public.html into the shell the Flask server fills in, and check it.
   - boot.js (a plain script that must run before the first paint) is minified and gets a content-hashed name;
   - the three server markers must be present exactly once (backend/app/seo/spa.py replaces them);
   - the page must contain nothing the CSP forbids (inline scripts, inline styles, style attributes, on* handlers);
   - the size budgets of docs/PLAN.md section 0 are enforced: first-screen JS <= 90 KB gzip, CSS <= 20 KB gzip;
   - the admin must not leak into the public page: no admin chunk, no editor, is reachable from public.html (plan section 0);
   - admin.html and preview.html get the same CSP checks (the server hands them out as they are);
   - stylesheets stay apart: the admin never gets the public page's layout rules and the public page never gets the admin's. */
import { createHash } from 'node:crypto'
import { readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { gzipSync } from 'node:zlib'
import { transform } from 'esbuild'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const dist = join(root, 'dist')
const htmlPath = join(dist, 'public.html')
const BUDGET = { js: 90 * 1024, css: 20 * 1024 }

const fail = (msg) => { console.error(`postbuild: ${msg}`); process.exit(1) }
const kb = (n) => `${(n / 1024).toFixed(1)} KB`
const gz = (buf) => gzipSync(buf, { level: 9 }).length

let html = readFileSync(htmlPath, 'utf8')

/* ---- boot.js ---------------------------------------------------------------------------------------------------------- */
const bootSrc = readFileSync(join(root, 'src/public/boot.js'), 'utf8')
const boot = await transform(bootSrc, { minify: true, target: 'es5', legalComments: 'none' })
const bootName = `assets/boot-${createHash('sha256').update(boot.code).digest('hex').slice(0, 8)}.js`
writeFileSync(join(dist, bootName), boot.code)
const bootTag = '<script src="/src/public/boot.js"></script>'
if (!html.includes(bootTag)) fail('the boot.js script tag is missing from public.html')
html = html.replace(bootTag, `<script src="/${bootName}"></script>`)
writeFileSync(htmlPath, html)

/* ---- the contract with the server ----------------------------------------------------------------------------------------- */
for (const marker of ['<!--bb:head-->', '<!--bb:data-->', '<!--bb:ssr-->']) {
  const n = html.split(marker).length - 1
  if (n !== 1) fail(`${marker} must appear exactly once in public.html (found ${n})`)
}
if (!/<div id="app">\s*<!--bb:ssr-->\s*<\/div>/.test(html)) fail('<!--bb:ssr--> must be the only content of <div id="app">')
if (html.indexOf('<!--bb:data-->') > html.indexOf(bootName)) fail('<!--bb:data--> must come before boot.js (boot.js reads it)')

/* ---- CSP: nothing inline ------------------------------------------------------------------------------------------------------ */
const scripts = [...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)]
for (const [, attrs, body] of scripts) {
  if (!/\bsrc=/.test(attrs) || body.trim()) fail(`inline script found: <script ${attrs.trim()}>`)
}
if (/<style\b/i.test(html)) fail('inline <style> found')
if (/\sstyle\s*=/i.test(html)) fail('a style attribute found')
if (/\son[a-z]+\s*=/i.test(html)) fail('an inline event handler found')

/* ---- budgets ------------------------------------------------------------------------------------------------------------------------ */
const refs = [...html.matchAll(/(?:src|href)="\/(assets\/[^"]+\.(?:js|css))"/g)].map((m) => m[1])
const sizes = { js: 0, css: 0 }
for (const ref of refs) {
  const type = ref.endsWith('.css') ? 'css' : 'js'
  const size = gz(readFileSync(join(dist, ref)))
  sizes[type] += size
  console.log(`  ${ref.padEnd(34)} ${kb(size).padStart(9)} gzip`)
}
console.log(`first screen: JS ${kb(sizes.js)} / ${kb(BUDGET.js)}, CSS ${kb(sizes.css)} / ${kb(BUDGET.css)}`)
if (sizes.js > BUDGET.js) fail(`first-screen JS is over budget (${kb(sizes.js)} > ${kb(BUDGET.js)})`)
if (sizes.css > BUDGET.css) fail(`CSS is over budget (${kb(sizes.css)} > ${kb(BUDGET.css)})`)

/* ---- the admin never reaches the public page --------------------------------------------------------------------------------- */
function staticImports(file, seen = new Set()) {
  if (seen.has(file)) return seen
  seen.add(file)
  const code = readFileSync(join(dist, file), 'utf8')
  for (const m of code.matchAll(/(?:from|import)\s*["']\.\/([^"']+\.js)["']/g)) staticImports(`assets/${m[1]}`, seen)
  return seen
}
const publicJs = refs.filter((r) => r.endsWith('.js') && !r.includes('/boot-'))
const reachable = new Set()
for (const r of publicJs) staticImports(r, reachable)
const leaked = [...reachable].filter((f) => /admin|editor|preview/i.test(f))
if (leaked.length) fail(`admin code is reachable from the public page: ${leaked.join(', ')}`)
console.log(`public page reaches ${reachable.size} scripts, none of them admin code`)

/* ---- admin.html and preview.html -------------------------------------------------------------------------------------------- */
function checkShell(name) {
  const text = readFileSync(join(dist, name), 'utf8')
  for (const [, attrs, body] of text.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)) {
    if (!/\bsrc=/.test(attrs) || body.trim()) fail(`inline script in ${name}`)
  }
  if (/<style\b/i.test(text) || /\sstyle\s*=/i.test(text) || /\son[a-z]+\s*=/i.test(text)) fail(`inline style or handler in ${name}`)
  return [...text.matchAll(/(?:src|href)="\/(assets\/[^"]+\.(?:js|css))"/g)].map((m) => m[1])
}
const adminRefs = checkShell('admin.html')
const previewRefs = checkShell('preview.html')
const admin = { js: 0, css: 0 }
for (const ref of adminRefs) admin[ref.endsWith('.css') ? 'css' : 'js'] += gz(readFileSync(join(dist, ref)))
console.log(`admin first screen: JS ${kb(admin.js)}, CSS ${kb(admin.css)} (the rest loads on demand, one chunk per page)`)
const cssOf = (list) => list.filter((r) => r.endsWith('.css')).map((r) => readFileSync(join(dist, r), 'utf8')).join('\n')
const publicCss = cssOf(refs)
const adminCss = cssOf(adminRefs)
const previewCss = cssOf(previewRefs)
if (!publicCss.includes('.site-header')) fail('the public stylesheet lost its layout rules (.site-header)')
if (adminCss.includes('.site-header') || adminCss.includes('.tabbar')) fail("the public page's layout rules reach the admin (they would restyle admin elements)")
if (publicCss.includes('.adm-') || previewCss.includes('.adm-')) fail("the admin's styles reach the public page")
if (!previewCss.includes('.site-header')) fail('the preview frame has no public stylesheet')

/* ---- everything else in assets/ is listed for the record ----------------------------------------------------------------- */
const all = readdirSync(join(dist, 'assets')).map((f) => [f, statSync(join(dist, 'assets', f)).size])
console.log(`dist/assets: ${all.length} files, ${kb(all.reduce((n, [, s]) => n + s, 0))} on disk`)
