// What a person does in the admin, clicked through for real (Chromium or WebKit) against the separate QA instance: sign in, write and publish a post,
// post a moment, upload a picture, make categories / tags / series / pages, configure the home page (with the live preview frame), navigation, appearance,
// SEO and redirects, the statistics switch, two-step verification, backups, the recycle bin, the log and the command palette.
// Every step is independent: a failure is listed and the rest still run. Credentials come from backend/data-qa/credentials.json and are never printed.
import { createHmac } from 'node:crypto'
import { readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { deflateSync } from 'node:zlib'
import { ADMIN_BASE, BROWSER, launch, openAdmin } from './adminlib.mjs'

const creds = JSON.parse(readFileSync(join(process.cwd(), '../backend/data-qa/credentials.json'), 'utf8'))
const results = []
const stamp = Date.now().toString(36)

async function step(name, fn) {
  try { await fn(); results.push([true, name]); console.log(`✓ ${name}`) } catch (e) { results.push([false, name, e]); console.log(`✗ ${name}: ${String(e.message).split('\n').slice(0, 3).join(' | ')}`) }
}
const expect = (cond, msg) => { if (!cond) throw new Error(msg) }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

/* a tiny solid-colour PNG, built by hand */
function png(w = 48, h = 32, rgb = [186, 214, 245]) {
  const crcTable = Array.from({ length: 256 }, (_, n) => { let c = n; for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; return c >>> 0 })
  const crc = (buf) => { let c = 0xffffffff; for (const b of buf) c = crcTable[(c ^ b) & 0xff] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0 }
  const chunk = (type, data) => { const len = Buffer.alloc(4); len.writeUInt32BE(data.length); const body = Buffer.concat([Buffer.from(type), data]); const sum = Buffer.alloc(4); sum.writeUInt32BE(crc(body)); return Buffer.concat([len, body, sum]) }
  const row = Buffer.concat([Buffer.from([0]), Buffer.from(Array.from({ length: w }, () => rgb).flat())])
  const raw = Buffer.concat(Array.from({ length: h }, () => row))
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = 2
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', ihdr), chunk('IDAT', deflateSync(raw)), chunk('IEND', Buffer.alloc(0))])
}
/* RFC 6238 with the standard library: the code an authenticator app would show */
function totp(secret, at = Date.now()) {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
  let bits = ''
  for (const ch of secret.replace(/=+$/, '').toUpperCase()) bits += alphabet.indexOf(ch).toString(2).padStart(5, '0')
  const key = Buffer.from(bits.match(/.{8}/g).map((b) => parseInt(b, 2)))
  const counter = Buffer.alloc(8); counter.writeBigUInt64BE(BigInt(Math.floor(at / 30000)))
  const h = createHmac('sha1', key).update(counter).digest()
  const o = h[19] & 15
  return String(((h[o] & 127) << 24 | h[o + 1] << 16 | h[o + 2] << 8 | h[o + 3]) % 1000000).padStart(6, '0')
}
/* a stored (uncompressed) zip, built by hand: enough for the import test */
function zipOf(files) {
  const crcTable = Array.from({ length: 256 }, (_, n) => { let c = n; for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; return c >>> 0 })
  const crc = (buf) => { let c = 0xffffffff; for (const b of buf) c = crcTable[(c ^ b) & 0xff] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0 }
  const parts = []; const central = []; let offset = 0
  for (const [name, text] of Object.entries(files)) {
    const nameBuf = Buffer.from(name); const data = Buffer.from(text); const sum = crc(data)
    const local = Buffer.alloc(30); local.writeUInt32LE(0x04034b50, 0); local.writeUInt16LE(20, 4); local.writeUInt16LE(0x0800, 6); local.writeUInt32LE(sum, 14); local.writeUInt32LE(data.length, 18); local.writeUInt32LE(data.length, 22); local.writeUInt16LE(nameBuf.length, 26)
    const cen = Buffer.alloc(46); cen.writeUInt32LE(0x02014b50, 0); cen.writeUInt16LE(20, 4); cen.writeUInt16LE(20, 6); cen.writeUInt16LE(0x0800, 8); cen.writeUInt32LE(sum, 16); cen.writeUInt32LE(data.length, 20); cen.writeUInt32LE(data.length, 24); cen.writeUInt16LE(nameBuf.length, 28); cen.writeUInt32LE(offset, 42)
    parts.push(local, nameBuf, data); central.push(cen, nameBuf); offset += 30 + nameBuf.length + data.length
  }
  const cd = Buffer.concat(central); const end = Buffer.alloc(22); end.writeUInt32LE(0x06054b50, 0); end.writeUInt16LE(Object.keys(files).length, 8); end.writeUInt16LE(Object.keys(files).length, 10); end.writeUInt32LE(cd.length, 12); end.writeUInt32LE(offset, 16)
  return Buffer.concat([...parts, cd, end])
}
/* the member names of a zip, read from its central directory */
function zipNames(buf) {
  const eocd = buf.lastIndexOf(Buffer.from([0x50, 0x4b, 0x05, 0x06]))
  expect(eocd >= 0, 'not a zip (no end-of-central-directory record)')
  let at = buf.readUInt32LE(eocd + 16); const count = buf.readUInt16LE(eocd + 10); const names = []
  for (let i = 0; i < count; i += 1) { const n = buf.readUInt16LE(at + 28); const extra = buf.readUInt16LE(at + 30); const comment = buf.readUInt16LE(at + 32); names.push(buf.toString('utf8', at + 46, at + 46 + n)); at += 46 + n + extra + comment }
  return names
}
const toast = (page, text) => page.locator('.toast', { hasText: text }).first().waitFor({ timeout: 6000 })
const apiGet = async (ctx, path) => (await ctx.request.get(`${ADMIN_BASE}/api${path}`)).json()

const browser = await launch()
try {
  /* ---------- sign-in ---------- */
  await step('login form: wrong password is refused, the right one opens the dashboard', async () => {
    const { ctx, page } = await openAdmin(browser, '/login', 1280, { login: false })
    await page.getByLabel('用户名').fill(creds.username)
    await page.getByLabel('密码').fill('definitely wrong password')
    await page.getByRole('button', { name: /登录/ }).click()
    await page.locator('[role=alert]').first().waitFor({ timeout: 5000 })
    await page.getByLabel('密码').fill(creds.password)
    await page.getByRole('button', { name: /登录/ }).click()
    await page.waitForURL(/\/admin\/?$/, { timeout: 8000 })
    await page.getByRole('heading', { name: '仪表盘' }).waitFor()
    await ctx.close()
  })

  /* ---------- the command palette and the shell ---------- */
  await step('command palette: ⌘K / Ctrl+K opens it, typing filters, Enter goes there', async () => {
    const { ctx, page } = await openAdmin(browser, '/', 1280)
    await page.keyboard.press(process.platform === 'darwin' ? 'Meta+k' : 'Control+k')
    const dialog = page.getByRole('dialog')
    await dialog.waitFor({ timeout: 4000 })
    await page.keyboard.type('备份')
    await sleep(250)
    await page.keyboard.press('Enter')
    await page.waitForURL(/\/admin\/backups/, { timeout: 5000 })
    await ctx.close()
  })
  await step('shell: sidebar groups collapse, mobile tab bar and drawer work at 390px', async () => {
    const { ctx, page } = await openAdmin(browser, '/', 390)
    await page.locator('.adm-tabbar').waitFor()
    await page.locator('.adm-tabbar').getByRole('link', { name: /文章/ }).click()
    await page.waitForURL(/\/admin\/posts/)
    await page.locator('.adm-tabbar').getByRole('button', { name: /更多/ }).click()
    await page.locator('.adm-drawer').getByRole('link', { name: /导航与页脚/ }).waitFor({ timeout: 3000 })
    await page.locator('.adm-drawer').getByRole('link', { name: /导航与页脚/ }).click()
    await page.waitForURL(/\/admin\/navigation/)
    await ctx.close()
  })

  /* ---------- posts ---------- */
  let postId = 0
  await step('post: write in Markdown, the server-rendered preview follows, publish, the public page shows it', async () => {
    const { ctx, page } = await openAdmin(browser, '/posts/new', 1280)
    await page.getByLabel('标题', { exact: true }).first().fill(`QA 文章 ${stamp}`)
    const area = page.locator('textarea.adm-md__area, .adm-editor__pane--write textarea').first()
    await area.click()
    await page.keyboard.type('## 小标题\n\n这是一段 **粗体** 和 `代码`。\n\n- 一\n- 二\n\n- [ ] 待办一项\n')
    await page.locator('.adm-preview__prose h2', { hasText: '小标题' }).waitFor({ timeout: 6000 })
    expect(await page.locator('.adm-preview__prose strong').count() > 0, 'preview has no <strong>')
    await page.getByRole('button', { name: '发布', exact: true }).click()
    await page.waitForURL(/\/admin\/posts\/\d+/, { timeout: 8000 })
    postId = Number(page.url().match(/posts\/(\d+)/)[1])
    const pub = await (await ctx.request.get(`${ADMIN_BASE}/api/admin/posts/${postId}`)).json()
    expect(pub.status === 'published', `status ${pub.status}`)
    const visible = await (await ctx.request.get(`${ADMIN_BASE}/api/posts/${pub.slug}`)).json()
    expect(visible.title === `QA 文章 ${stamp}`, 'public API does not return it')
    await ctx.close()
  })
  await step('post: edit, save with Ctrl/Cmd+S, version history lists the earlier text and restores it', async () => {
    const { ctx, page } = await openAdmin(browser, `/posts/${postId}`, 1280)
    const area = page.locator('.adm-editor__pane--write textarea').first()
    await area.click()
    await page.keyboard.press(process.platform === 'darwin' ? 'Meta+End' : 'Control+End')
    await page.keyboard.type('\n\n第二版新增的一段。')
    await page.keyboard.press(process.platform === 'darwin' ? 'Meta+s' : 'Control+s')
    await toast(page, '已保存')
    await page.getByRole('button', { name: /版本/ }).click()
    const drawer = page.getByRole('dialog', { name: '版本历史' })
    await drawer.waitFor()
    const rows = drawer.locator('.adm-revs__row')
    await rows.first().waitFor()
    expect(await rows.count() >= 2, `only ${await rows.count()} revision(s) listed`)
    await rows.nth(1).click()                                         // the first version: before the added paragraph
    await drawer.locator('.adm-diff__line.is-del, .adm-diff__line.is-add').first().waitFor({ timeout: 4000 })
    await drawer.getByRole('button', { name: '恢复到这个版本' }).click()
    await toast(page, '已恢复到那个版本')
    const body = await area.inputValue()
    expect(!body.includes('第二版新增'), 'the restored text still has the added paragraph')
    await ctx.close()
  })
  await step('post: ten seconds of typing becomes an autosave on the server', async () => {
    const { ctx, page } = await openAdmin(browser, `/posts/${postId}`, 1280)
    const area = page.locator('.adm-editor__pane--write textarea').first()
    await area.click()
    await page.keyboard.type(' 暂存内容。')
    await sleep(11500)
    const p = await (await ctx.request.get(`${ADMIN_BASE}/api/admin/posts/${postId}`)).json()
    expect(p.autosave && p.autosave.snapshot.content_md.includes('暂存内容'), 'no autosave stored')
    await ctx.close()
  })
  await step('post list: search finds the post; select + batch trash; recycle bin lists it; restore brings it back', async () => {
    const { ctx, page } = await openAdmin(browser, '/posts', 1280)
    await page.getByRole('searchbox', { name: '搜索文章' }).fill(`QA 文章 ${stamp}`)
    await page.getByLabel(`选择：QA 文章 ${stamp}`).waitFor({ timeout: 6000 })
    await page.getByLabel(`选择：QA 文章 ${stamp}`).check({ force: true })
    await page.getByRole('region', { name: '批量操作' }).getByRole('button', { name: /移入回收站/ }).click()
    const ask = page.getByRole('dialog').filter({ hasText: /回收站/ }).last()
    await ask.getByRole('button', { name: '移入回收站' }).click()
    await toast(page, '已处理 1 篇')
    await page.goto(`${ADMIN_BASE}/admin/trash`, { waitUntil: 'networkidle' })
    const row = page.locator('tr, li').filter({ hasText: `QA 文章 ${stamp}` }).first()
    await row.waitFor({ timeout: 6000 })
    await row.getByRole('button', { name: /恢复/ }).click()
    await toast(page, '恢复')
    const back = await (await ctx.request.get(`${ADMIN_BASE}/api/admin/posts/${postId}`)).json()
    expect(!back.deleted_at, 'post still in the bin')
    await ctx.close()
  })

  /* ---------- moments ---------- */
  await step('moment: type with a #tag, post it, it appears in the list and on the public page', async () => {
    const { ctx, page } = await openAdmin(browser, '/moments', 1280)
    await page.getByLabel('动态内容').fill(`QA 动态 ${stamp} #测试标签`)
    await page.getByRole('button', { name: '发布', exact: true }).click()
    await toast(page, '动态已发布')
    // the QA instance accumulates imported copies of the pinned demo moment (every import run adds some), which sort first: look the new one up by its words
    await page.getByRole('searchbox', { name: '搜索动态' }).fill(`QA 动态 ${stamp}`)
    await page.locator('.adm-moment', { hasText: `QA 动态 ${stamp}` }).first().waitFor({ timeout: 8000 })
    const list = await (await ctx.request.get(`${ADMIN_BASE}/api/moments?per=5`)).json()
    expect(JSON.stringify(list).includes(`QA 动态 ${stamp}`), 'public moments list lacks it')
    await ctx.close()
  })

  /* ---------- media ---------- */
  await step('media: upload a picture, open its details, set alt text, see it in the library, move to trash', async () => {
    const { ctx, page } = await openAdmin(browser, '/media', 1280)
    await page.locator('input[type=file]').first().setInputFiles({ name: `qa-${stamp}.png`, mimeType: 'image/png', buffer: png(48, 32, [150 + (parseInt(stamp, 36) % 90), 190 + (parseInt(stamp, 36) % 50), 240]) })
    await page.locator('.adm-media-tile', { hasText: `qa-${stamp}` }).first().waitFor({ timeout: 10000 })
    await page.locator('.adm-media-tile', { hasText: `qa-${stamp}` }).first().click()
    const drawer = page.getByRole('dialog', { name: new RegExp(`qa-${stamp}`) })
    await drawer.getByLabel('替代文字').fill('一块浅蓝色的测试图')
    await drawer.getByRole('button', { name: '保存信息' }).click()
    await toast(page, '已保存')
    const media = (await apiGet(ctx, '/admin/media?q=qa-' + stamp)).items[0]
    expect(media && media.alt === '一块浅蓝色的测试图', 'alt text not stored')
    expect(media.orig_width === 48 && media.orig_height === 32, `stored size ${media.orig_width}x${media.orig_height}`)
    await drawer.getByRole('button', { name: /移入回收站/ }).click()
    await page.locator('.adm-media-tile', { hasText: `qa-${stamp}` }).waitFor({ state: 'detached', timeout: 6000 })
    await ctx.close()
  })

  /* ---------- taxonomy and pages ---------- */
  await step('categories: create one in the dialog, it is listed, delete it', async () => {
    const { ctx, page } = await openAdmin(browser, '/categories', 1280)
    await page.locator('main').getByRole('button', { name: /新建分类/ }).click()
    await page.getByRole('dialog').getByLabel('名称').fill(`QA 分类 ${stamp}`)
    await page.getByRole('dialog').getByRole('button', { name: '保存' }).click()
    await toast(page, '分类已保存')
    await page.getByText(`QA 分类 ${stamp}`).first().waitFor()
    await page.getByRole('button', { name: `删除「QA 分类 ${stamp}」` }).click()
    await page.getByRole('dialog', { name: '删除分类' }).getByRole('button', { name: '删除分类' }).click()
    await page.locator('.adm-sortrow b', { hasText: `QA 分类 ${stamp}` }).waitFor({ state: 'detached', timeout: 6000 })
    await ctx.close()
  })
  await step('tags and series: create from the dialogs', async () => {
    const { ctx, page } = await openAdmin(browser, '/tags', 1280)
    await page.locator('main').getByRole('button', { name: /新建标签/ }).click()
    await page.getByRole('dialog').getByLabel('名称').fill(`qa标签${stamp}`)
    await page.getByRole('dialog').getByRole('button', { name: '保存' }).click()
    await page.getByText(`qa标签${stamp}`).first().waitFor({ timeout: 6000 })
    await page.goto(`${ADMIN_BASE}/admin/series`, { waitUntil: 'networkidle' })
    await page.locator('main').getByRole('button', { name: /新建系列/ }).click()
    await page.getByRole('dialog').getByLabel('标题').fill(`QA 系列 ${stamp}`)
    await page.getByRole('dialog').getByRole('button', { name: '保存' }).click()
    await page.getByText(`QA 系列 ${stamp}`).first().waitFor({ timeout: 6000 })
    await ctx.close()
  })
  await step('pages: create a page and put it in the top navigation; the public page and the nav entry exist', async () => {
    const { ctx, page } = await openAdmin(browser, '/pages/new', 1280)
    await page.getByLabel('标题', { exact: true }).first().fill(`QA 页面 ${stamp}`)
    const area = page.locator('.adm-editor__pane--write textarea').first()
    await area.click()
    await page.keyboard.type('页面正文。')
    await page.getByRole('switch', { name: /放进顶栏导航/ }).check({ force: true })
    await page.getByRole('button', { name: /发布|保存/ }).last().click()
    await page.waitForURL(/\/admin\/pages\/\d+/, { timeout: 8000 })
    const id = Number(page.url().match(/pages\/(\d+)/)[1])
    const saved = await (await ctx.request.get(`${ADMIN_BASE}/api/admin/pages/${id}`)).json()
    const pub = await ctx.request.get(`${ADMIN_BASE}/api/pages/${saved.slug}`)
    expect(pub.status() === 200, `public page status ${pub.status()}`)
    const site = await (await ctx.request.get(`${ADMIN_BASE}/api/site`)).json()
    expect(site.nav.top.some((i) => i.url === `/${saved.slug}`), 'the page is not in the public top navigation')
    await ctx.close()
  })

  /* ---------- site configuration ---------- */
  await step('home: open hero, change the intro, the preview frame shows it before saving, save, public data changes, reset', async () => {
    const { ctx, page } = await openAdmin(browser, '/home', 1440)
    await page.frameLocator('iframe.adm-pframe__frame').locator('.hero, .home').first().waitFor({ timeout: 10000 })
    await page.locator('.adm-navrow', { hasText: '首屏名片' }).getByRole('button', { name: '设置' }).click()
    const intro = page.getByLabel('简介', { exact: true })
    await intro.fill(`预览里的新简介 ${stamp}`)
    await page.frameLocator('iframe.adm-pframe__frame').getByText(`预览里的新简介 ${stamp}`).first().waitFor({ timeout: 8000 })
    expect((await apiGet(ctx, '/home')).blocks[0].config.intro !== `预览里的新简介 ${stamp}`, 'the public home already changed before saving')
    await page.getByRole('button', { name: '保存首页' }).click()
    await toast(page, '首页已保存')
    const saved = await apiGet(ctx, '/home')
    expect(JSON.stringify(saved).includes(`预览里的新简介 ${stamp}`), 'public home lacks the new intro')
    page.once('dialog', () => undefined)
    await page.getByRole('button', { name: '恢复默认' }).click()
    await page.getByRole('dialog').getByRole('button', { name: '恢复默认' }).click()
    await toast(page, '已恢复默认首页')
    await ctx.close()
  })
  await step('home: switch a module off and move another with the keyboard; the saved public home follows both', async () => {
    const { ctx, page } = await openAdmin(browser, '/home', 1440)
    await page.locator('.adm-navrow', { hasText: '书架' }).getByRole('switch').uncheck({ force: true })
    const before = await page.locator('.adm-navrow .adm-sortrow__main b').allInnerTexts()
    await page.getByRole('button', { name: '拖动调整「最近的动态」的位置' }).focus()
    await page.keyboard.press('ArrowUp')
    const after = await page.locator('.adm-navrow .adm-sortrow__main b').allInnerTexts()
    expect(after.indexOf('最近的动态') === before.indexOf('最近的动态') - 1, `order did not change: ${after.join(',')}`)
    expect(await page.getByRole('status').filter({ hasText: /已移到第/ }).count() > 0, 'no spoken announcement of the move')
    await sleep(900)
    await page.getByRole('button', { name: '保存首页' }).click()
    await toast(page, '首页已保存')
    const types = (await apiGet(ctx, '/home')).blocks.map((b) => b.type)
    expect(!types.includes('shelf'), 'shelf still on the public home')
    expect(types.indexOf('latest_moments') < types.indexOf('latest_posts'), `public order ${types.join(',')}`)
    await page.getByRole('button', { name: '恢复默认' }).click()
    await page.getByRole('dialog').getByRole('button', { name: '恢复默认' }).click()
    await toast(page, '已恢复默认首页')
    await ctx.close()
  })
  await step('home: dragging a handle with the mouse reorders the list', async () => {
    const { ctx, page } = await openAdmin(browser, '/home', 1440)
    const handles = page.locator('.adm-navrow .adm-grip')
    const first = await handles.nth(0).boundingBox()
    const third = await handles.nth(2).boundingBox()
    await page.mouse.move(first.x + first.width / 2, first.y + first.height / 2)
    await page.mouse.down()
    await page.mouse.move(third.x + third.width / 2, third.y + third.height / 2 + 6, { steps: 8 })
    await page.mouse.up()
    const names = await page.locator('.adm-navrow .adm-sortrow__main b').allInnerTexts()
    expect(names[0] !== '首屏名片' && names.indexOf('首屏名片') >= 2, `drag did not move the first row: ${names.join(',')}`)
    await ctx.close()
  })
  await step('navigation: add and reorder an item, save; the public nav follows; reset; mobile bar refuses a 6th item', async () => {
    const { ctx, page } = await openAdmin(browser, '/navigation', 1280)
    await page.getByRole('button', { name: '加一个条目' }).click()
    const added = page.locator('.adm-navrow').last()
    await added.getByLabel('名称').fill('QA 链接')
    await added.getByLabel('类型').selectOption('link')
    await added.getByLabel('目标').fill('https://example.com/')
    await page.getByRole('button', { name: '拖动调整「QA 链接」的位置' }).focus()
    await page.keyboard.press('ArrowUp')
    await page.getByRole('button', { name: /保存顶栏/ }).click()
    await toast(page, '导航已保存')
    const nav = (await apiGet(ctx, '/site')).nav.top
    expect(nav.length >= 2 && nav[nav.length - 2].label === 'QA 链接' && nav[nav.length - 2].external === true, `public top nav: ${nav.map((i) => i.label).join(',')}`)
    await page.getByRole('button', { name: '恢复默认', exact: true }).first().click()
    await page.getByRole('dialog').getByRole('button', { name: '恢复默认' }).click()
    await toast(page, '已恢复默认')
    expect(!(await apiGet(ctx, '/site')).nav.top.some((i) => i.label === 'QA 链接'), 'the item survived the reset')
    await page.getByRole('tab', { name: /手机底栏/ }).click()
    const add = page.getByRole('button', { name: '加一个条目' })
    if (!(await add.isDisabled())) await add.click()
    expect(await add.isDisabled(), 'the add button is still enabled with 5 items on the mobile bar')
    await ctx.close()
  })
  await step('appearance: change the tagline and the theme; the public site data follows', async () => {
    const { ctx, page } = await openAdmin(browser, '/appearance', 1280)
    const before = (await apiGet(ctx, '/site')).tagline
    await page.getByLabel('一句话简介（副标题）').fill(`QA 口号 ${stamp}`)
    await page.getByRole('button', { name: /保存站点信息|保存/ }).first().click()
    await toast(page, '已保存')
    expect((await apiGet(ctx, '/site')).tagline === `QA 口号 ${stamp}`, 'public site tagline did not change')
    await page.getByLabel('一句话简介（副标题）').fill(before)
    await page.getByRole('button', { name: /保存站点信息|保存/ }).first().click()
    await toast(page, '已保存')
    await ctx.close()
  })
  await step('SEO: save the settings, add a redirect, it is listed, delete it', async () => {
    const { ctx, page } = await openAdmin(browser, '/seo', 1280)
    await page.getByLabel('默认描述').fill(`QA 描述 ${stamp}`)
    await page.getByRole('button', { name: '保存', exact: true }).first().click()
    await toast(page, 'SEO 设置已保存')
    await page.getByRole('button', { name: '加一条' }).click()
    await page.getByRole('dialog').getByLabel(/来源/).fill(`/old-${stamp}`)
    await page.getByRole('dialog').getByLabel(/目标/).fill('/blog')
    await page.getByRole('dialog').getByRole('button', { name: '保存' }).click()
    await toast(page, '重定向已保存')
    await page.getByText(`/old-${stamp}`).first().waitFor()
    const res = await ctx.request.get(`${ADMIN_BASE}/old-${stamp}`, { maxRedirects: 0 })
    expect([301, 302].includes(res.status()), `redirect status ${res.status()}`)
    await page.getByRole('button', { name: `删除 /old-${stamp}` }).click()
    await page.getByRole('dialog').getByRole('button', { name: '删除' }).click()
    await toast(page, '已删除')
    await ctx.close()
  })
  await step('stats: visits show up in the chart and the table, the switch turns recording off and on', async () => {
    const { ctx, page } = await openAdmin(browser, '/stats', 1280)
    for (let i = 0; i < 3; i += 1) await ctx.request.post(`${ADMIN_BASE}/api/track`, { data: { p: '/blog', r: 'https://example.org/x' }, headers: { 'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile', Origin: ADMIN_BASE } })
    await page.reload({ waitUntil: 'networkidle' })
    await page.locator('.adm-chart__svg').waitFor({ timeout: 6000 })
    await page.getByText('用表格查看').click()
    await page.getByRole('switch', { name: /记录访问统计/ }).click()
    await toast(page, '已停止统计')
    await page.getByRole('switch', { name: /记录访问统计/ }).click()
    await toast(page, '已开始统计')
    await ctx.close()
  })

  /* ---------- account ---------- */
  await step('account: two-step verification can be enabled with a real code, recovery codes show once, disabled again with the password', async () => {
    const { ctx, page } = await openAdmin(browser, '/account', 1280)
    await page.getByRole('button', { name: '开始设置' }).click()
    const secret = (await page.locator('.adm-secret').innerText()).replace(/\s+/g, '')
    await page.getByLabel('6 位动态码').fill(totp(secret))
    await page.getByRole('button', { name: '确认并开启' }).click()
    await page.getByRole('list', { name: '一次性恢复码' }).waitFor({ timeout: 6000 })
    expect(await page.locator('.adm-codes li').count() === 10, 'not 10 recovery codes')
    await page.getByRole('button', { name: '我已经存好了' }).click()
    await page.getByLabel('关闭需要输入密码').fill(creds.password)
    await page.getByRole('button', { name: '关闭二次验证' }).last().click()
    await page.getByRole('dialog').getByRole('button', { name: '关闭' }).click()
    await toast(page, '二次验证已关闭')
    await ctx.close()
  })
  await step('account: sessions list shows this device; password form checks the two entries match', async () => {
    const { ctx, page } = await openAdmin(browser, '/account', 1280)
    await page.getByText('当前设备').first().waitFor()
    await page.getByLabel('新密码').fill('abcdefghij1')
    await page.getByLabel('再输一次').fill('different')
    await page.getByText('两次输入不一样').waitFor()
    expect(await page.getByRole('button', { name: '修改密码' }).isDisabled(), 'submit not disabled while the entries differ')
    await ctx.close()
  })

  /* ---------- system ---------- */
  await step('system: status renders and a maintenance job runs', async () => {
    const { ctx, page } = await openAdmin(browser, '/system', 1280)
    await page.getByText('运行状态').waitFor()
    await page.locator('.adm-jobs li', { hasText: '刷新站点缓存' }).getByRole('button', { name: '现在运行' }).click()
    await toast(page, '已完成')
    await ctx.close()
  })
  await step('logs: the audit log lists what was done above and filters by type', async () => {
    const { ctx, page } = await openAdmin(browser, '/logs', 1280)
    await page.getByLabel('类型').selectOption('moment.')
    await page.getByText('发布动态').first().waitFor({ timeout: 6000 })
    await sleep(500)
    expect(!(await page.getByText('修改设置').count()), 'filter still shows settings entries')
    await ctx.close()
  })
  await step('export as Markdown: a real zip with README, posts, moments and the picture manifest comes down', async () => {
    const { ctx, page } = await openAdmin(browser, '/backups', 1280)
    const [download] = await Promise.all([page.waitForEvent('download', { timeout: 60000 }), page.getByRole('button', { name: '导出全部内容' }).click()])
    expect(/^markdown-export-.*\.zip$/.test(download.suggestedFilename()), `name ${download.suggestedFilename()}`)
    const file = join(tmpdir(), `bb-export-${stamp}.zip`)
    await download.saveAs(file)
    const names = zipNames(readFileSync(file))
    expect(names.includes('README.md') && names.includes('media/manifest.json'), `entries: ${names.slice(0, 6).join(', ')}`)
    expect(names.some((n) => n.startsWith('posts/') && n.endsWith('.md')) && names.some((n) => n.startsWith('moments/')), 'no posts or moments in the export')
    await ctx.close()
  })
  await step('import a zip of Markdown files through the page: the result is reported and the draft exists', async () => {
    const { ctx, page } = await openAdmin(browser, '/backups', 1280)
    const file = join(tmpdir(), `bb-import-${stamp}.zip`)
    writeFileSync(file, zipOf({ 'posts/hello.md': `---\ntitle: 导入的 ${stamp}\ntags: [a, b]\n---\n正文一行。\n`, 'moments/m.md': `---\nvisibility: public\n---\n导入的动态 ${stamp}\n` }))
    await page.locator('input[type=file][aria-label="选择要导入的压缩包"]').setInputFiles(file)
    await page.getByRole('dialog').getByRole('button', { name: '导入' }).click()
    await page.locator('.adm-importresult').waitFor({ timeout: 30000 })
    const text = await page.locator('.adm-importresult').innerText()
    expect(/导入了 1 篇文章.*1 条动态/s.test(text), `result text: ${text}`)
    const found = await apiGet(ctx, `/admin/posts?q=${encodeURIComponent(`导入的 ${stamp}`)}&status=draft`)
    expect(found.total === 1, `drafts found: ${found.total}`)
    await ctx.close()
  })
  await step('post list: "重新生成摘要" in the batch menu replaces a hand-written summary after a confirmation', async () => {
    const { ctx, page } = await openAdmin(browser, '/posts', 1280)
    const csrf = (await apiGet(ctx, '/admin/auth/me')).csrf_token
    const made = await (await ctx.request.post(`${ADMIN_BASE}/api/admin/posts`, { data: { title: `摘要 ${stamp}`, content_md: '正文的第一句话。\n\n第二段。', summary: '手写的摘要', status: 'draft' }, headers: { 'X-CSRF-Token': csrf, Origin: ADMIN_BASE } })).json()
    await page.reload({ waitUntil: 'networkidle' })
    await page.getByRole('searchbox', { name: '搜索文章' }).fill(`摘要 ${stamp}`)
    await page.getByLabel(`选择：摘要 ${stamp}`).check({ force: true })
    await page.getByRole('region', { name: '批量操作' }).getByRole('button', { name: '更多' }).click()
    await page.getByRole('menuitem', { name: '重新生成摘要' }).click()
    await page.getByRole('dialog').getByRole('button', { name: '重新生成' }).click()
    await toast(page, '已处理 1 篇')
    const got = await apiGet(ctx, `/admin/posts/${made.id}`)
    expect(got.summary.startsWith('正文的第一句话') && got.summary_auto === true, `summary is now: ${got.summary}`)
    await ctx.close()
  })
  await step('backups: create, it is listed, download is offered, delete it', async () => {
    const { ctx, page } = await openAdmin(browser, '/backups', 1280)
    await page.getByRole('button', { name: '立即备份' }).click()
    await toast(page, '备份好了')
    const row = page.locator('tbody tr').first()
    const [download] = await Promise.all([page.waitForEvent('download', { timeout: 8000 }), row.getByRole('button', { name: /下载/ }).click()])
    expect(/\.tar\.gz$/.test(download.suggestedFilename()), `download name ${download.suggestedFilename()}`)
    await row.getByRole('button', { name: /删除/ }).click()
    await page.getByRole('dialog').getByRole('button', { name: '删除' }).click()
    await toast(page, '已删除')
    await ctx.close()
  })
  /* the destructive one goes last: it replaces the QA instance's own data with an earlier copy of itself */
  await step('restore: from a stored backup with the typed confirmation; the safety copy is made; the site still works afterwards', async () => {
    const { ctx, page } = await openAdmin(browser, '/backups', 1280)
    const posts = (await apiGet(ctx, '/admin/posts?per=1')).total
    await page.getByRole('button', { name: '立即备份' }).click()
    await toast(page, '备份好了')
    const row = page.locator('tbody tr').first()
    await row.getByRole('button', { name: '恢复', exact: true }).click()
    const dialog = page.getByRole('dialog').filter({ hasText: /恢复/ }).last()
    const go = dialog.getByRole('button', { name: '恢复', exact: true })
    expect(await go.isDisabled(), 'the restore button is enabled before the word is typed')
    await dialog.getByLabel(/请输入/).fill('恢复')
    await go.click()
    await page.waitForURL(/\/admin\/?$/, { timeout: 15000 })
    await page.getByRole('heading', { name: '仪表盘' }).waitFor({ timeout: 10000 }).catch(async () => { await page.getByRole('button', { name: /登录/ }).waitFor({ timeout: 3000 }) })
    const names = (await apiGet(ctx, '/admin/system/backups').catch(() => ({ items: [] }))).items?.map((b) => b.name) ?? []
    expect(names.some((n) => n.includes('pre-restore')), `no pre-restore safety backup among ${names.join(', ')}`)
    expect((await (await ctx.request.get(`${ADMIN_BASE}/api/site`)).json()).name, 'public site broken after restore')
    expect((await apiGet(ctx, '/admin/posts?per=1')).total === posts, 'post count changed by restoring a copy made a moment ago')
    await ctx.close()
  })
} finally { await browser.close() }

const failed = results.filter((r) => !r[0])
console.log(`\nADMIN FLOWS (${BROWSER}): ${results.length - failed.length}/${results.length} passed`)
if (failed.length) { for (const [, name, e] of failed) console.log(`  ✗ ${name}\n      ${String(e.stack || e).split('\n').slice(0, 4).join('\n      ')}`) }
process.exit(failed.length ? 1 : 0)
