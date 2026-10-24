// Regressions for record identity and edits made while a save response is in flight. Only touches this run's own QA drafts.
import assert from 'node:assert/strict'
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { ADMIN_BASE, BROWSER, launch, openAdmin } from './adminlib.mjs'

const browser = await launch()
const { ctx, page, errors } = await openAdmin(browser, '/')
const me = await (await ctx.request.get(`${ADMIN_BASE}/api/admin/auth/me`)).json()
const headers = { Origin: ADMIN_BASE, 'X-CSRF-Token': me.csrf_token }
const created = []
const stamp = Date.now()
const output = resolve('../docs/agent-memory/audits/2026-10-24-risk-fixes')
mkdirSync(output, { recursive: true })
const api = async (method, path, data) => {
  const r = await ctx.request[method](`${ADMIN_BASE}/api/admin${path}`, { headers, data })
  assert(r.ok(), `${method} ${path}: ${r.status()}`)
  return r.json()
}
const title = () => page.getByLabel('标题', { exact: true }).first()
const body = () => page.locator('.adm-md__area')
const save = () => page.getByRole('button', { name: '保存', exact: true })
async function bounded(promise) {
  let timer
  try {
    return await Promise.race([promise, new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('held request did not arrive within 10 seconds')), 10_000) })])
  } finally { clearTimeout(timer) }
}
const settled = () => page.waitForFunction(() => !document.querySelector('.adm-editor__state')?.textContent?.includes('正在保存'))
async function newMenu(label) {
  await page.getByRole('button', { name: '新建', exact: true }).click()
  await page.getByRole('menuitem', { name: label, exact: true }).click()
}
async function holdSave(kind, id) {
  let release, reached
  const gate = new Promise(r => { release = r })
  const pending = new Promise(r => { reached = r })
  const pattern = `**/api/admin/${kind}${id ? `/${id}` : ''}`
  await page.route(pattern, async route => {
    if (route.request().method() !== (id ? 'PATCH' : 'POST')) return route.continue()
    const response = await route.fetch()
    const record = await response.json()
    if (!id) created.push([kind, record.id])
    reached(record)
    await gate
    await route.fulfill({ response })
  })
  return { pending, release, clear: () => page.unroute(pattern) }
}
let checks = 0
const passed = (name) => { checks++; console.log(`✓ ${name}`) }
try {
  for (const [kind, label] of [['posts', '文章'], ['pages', '页面']]) {
    const original = await api('post', `/${kind}`, { title: `risk-fix-${stamp}-${kind}`, status: 'draft', content_md: 'original body' })
    created.push([kind, original.id])
    await page.goto(`${ADMIN_BASE}/admin/${kind}/${original.id}`, { waitUntil: 'networkidle' })
    assert.equal(await title().inputValue(), original.title)
    await newMenu(label)
    await page.waitForURL(`**/admin/${kind}/new`)
    assert.equal(await title().inputValue(), '')
    assert.equal(await body().inputValue(), '')
    await title().fill(`risk-fix-new-${stamp}-${kind}`)
    // Pages default to published; all records made by this script stay drafts.
    if (kind === 'pages') await page.getByRole('radio', { name: '草稿', exact: true }).click()
    const response = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith(`/api/admin/${kind}`))
    await save().click()
    const newRecord = await (await response).json()
    created.push([kind, newRecord.id])
    await page.waitForURL(`**/admin/${kind}/${newRecord.id}`)
    assert.notEqual(newRecord.id, original.id)
    assert.equal((await api('get', `/${kind}/${original.id}`)).title, original.title)
    passed(`${kind}: New clears identity and POST leaves the original unchanged`)

    const held = await holdSave(kind, newRecord.id)
    await title().fill('submitted title')
    await body().fill('submitted body')
    await save().click()
    await bounded(held.pending)
    await title().fill('typed during save')
    await body().fill('body typed during save')
    held.release()
    await settled()
    assert.equal(await title().inputValue(), 'typed during save')
    assert.equal(await body().inputValue(), 'body typed during save')
    assert(await save().isEnabled(), 'newer edits must stay dirty')
    await held.clear()
    const patch = page.waitForResponse(r => r.request().method() === 'PATCH' && r.url().endsWith(`/api/admin/${kind}/${newRecord.id}`))
    await save().click()
    assert((await patch).ok())
    await settled()
    assert.equal((await api('get', `/${kind}/${newRecord.id}`)).content_md, 'body typed during save')
    passed(`${kind}: delayed PATCH preserves input and a second save persists it`)
    await page.locator('.adm-preview__prose').filter({ hasText: 'body typed during save' }).waitFor()
    await page.screenshot({ path: `${output}/${BROWSER}-${kind}-saved.png`, fullPage: true })

    await title().fill('unsaved work')
    await newMenu(label)
    await page.getByRole('dialog').getByRole('button', { name: '留下', exact: true }).click()
    assert.equal(await title().inputValue(), 'unsaved work')
    await newMenu(label)
    await page.getByRole('dialog').getByRole('button', { name: '离开', exact: true }).click()
    await page.waitForURL(`**/admin/${kind}/new`)
    assert.equal(await title().inputValue(), '')
    passed(`${kind}: dirty navigation can be cancelled or confirmed`)

    const firstSave = await holdSave(kind)
    await title().fill(`risk-fix-first-${stamp}-${kind}`)
    if (kind === 'pages') await page.getByRole('radio', { name: '草稿', exact: true }).click()
    await save().click()
    const firstRecord = await bounded(firstSave.pending)
    await title().fill('typing through first save')
    await body().fill('new body through first save')
    firstSave.release()
    await page.waitForURL(`**/admin/${kind}/${firstRecord.id}`)
    await settled()
    assert.equal(await title().inputValue(), 'typing through first save')
    assert.equal(await body().inputValue(), 'new body through first save')
    assert(await save().isEnabled())
    assert.equal(await page.getByRole('dialog').count(), 0, 'own first-save navigation must not ask to discard')
    await firstSave.clear()
    passed(`${kind}: delayed first POST keeps newer input across its route replacement`)

    // Ignore a late response after explicitly discarding this editor to start another record.
    await save().click()
    await settled()
    const obsolete = await holdSave(kind, firstRecord.id)
    await title().fill('obsolete response')
    await save().click()
    await bounded(obsolete.pending)
    await newMenu(label)
    await page.getByRole('dialog').getByRole('button', { name: '离开', exact: true }).click()
    await page.waitForURL(`**/admin/${kind}/new`)
    obsolete.release()
    await page.waitForTimeout(250)
    assert.equal(await title().inputValue(), '')
    assert(page.url().endsWith(`/${kind}/new`))
    await obsolete.clear()
    passed(`${kind}: late save response cannot repopulate a new editor`)

    let releaseLoad, reachedLoad
    const loadGate = new Promise(r => { releaseLoad = r })
    const loading = new Promise(r => { reachedLoad = r })
    const loadPattern = `**/api/admin/${kind}/${original.id}`
    await page.route(loadPattern, async route => {
      if (route.request().method() !== 'GET') return route.continue()
      const response = await route.fetch()
      reachedLoad()
      await loadGate
      await route.fulfill({ response })
    })
    await page.goto(`${ADMIN_BASE}/admin/${kind}/${original.id}`, { waitUntil: 'domcontentloaded' })
    await bounded(loading)
    await newMenu(label)
    await page.waitForURL(`**/admin/${kind}/new`)
    releaseLoad()
    await page.waitForTimeout(250)
    assert.equal(await title().inputValue(), '')
    assert.equal(await body().inputValue(), '')
    await page.unroute(loadPattern)
    passed(`${kind}: late record load cannot populate a new editor`)
  }
  const post = created.find(([kind]) => kind === 'posts')[1]
  await page.goto(`${ADMIN_BASE}/admin/posts/${post}`, { waitUntil: 'networkidle' })
  await api('patch', `/posts/${post}`, { title: 'saved in another window' })
  await title().fill('confirmed conflict overwrite')
  await save().click()
  const forced = page.waitForResponse(r => r.request().method() === 'PATCH' && r.url().endsWith(`/api/admin/posts/${post}`) && r.status() === 200)
  await page.getByRole('button', { name: '用我的覆盖', exact: true }).click()
  await forced
  await settled()
  assert.equal((await api('get', `/posts/${post}`)).title, 'confirmed conflict overwrite')
  passed('posts: confirmed conflict retry actually saves')
  assert.equal(errors.filter(e => e.startsWith('pageerror:')).length, 0, errors.join('\n'))
  console.log(`${BROWSER}: ${checks}/${checks} editor regressions passed`)
} finally {
  await page.close()
  for (const [kind, id] of created) {
    await api('delete', `/${kind}/${id}`)
    await api('delete', `/${kind}/${id}/purge`)
  }
  await ctx.close()
  await browser.close()
}
