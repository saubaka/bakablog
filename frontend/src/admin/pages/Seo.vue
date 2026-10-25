<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { api, AdminError } from '../api/client'
import { ago } from '../format'
import { loadSettings, saveGroup } from '../settings'
import type { ListPage, RedirectRow, SettingsGroups } from '../types'
import AIcon from '../ui/AIcon'
import { confirm } from '../ui/confirm'
import EmptyBox from '../ui/EmptyBox.vue'
import Field from '../ui/Field.vue'
import MediaField from '../ui/MediaField.vue'
import Modal from '../ui/Modal.vue'
import TableWrap from '../ui/TableWrap.vue'
import PageHead from '../ui/PageHead.vue'
import Pagination from '../ui/Pagination.vue'
import Segmented from '../ui/Segmented.vue'
import SwitchField from '../ui/SwitchField.vue'
import TagInput from '../ui/TagInput.vue'
import { toast, toastError } from '../ui/toast'
import { debounced, useSubmit } from '../use'

const loaded = ref(false)
const origin = ref('')
const seo = reactive<SettingsGroups['seo']>({ title: '', description: '', keywords: [], share_image_media_id: null, robots_extra: '', sitemap: { moments: true, pages: true, taxonomy: true } })
const errors = ref<Record<string, string>>({})
const busy = ref(false)
onMounted(async () => { try { Object.assign(seo, JSON.parse(JSON.stringify((await loadSettings()).groups.seo))); loaded.value = true; origin.value = (await api.get<{ site_url: string }>('/system/status')).site_url } catch (e) { toastError(e instanceof AdminError ? e.message : '设置加载失败。') } })
async function saveSeo(): Promise<void> {
  busy.value = true
  errors.value = {}
  try { await saveGroup('seo', { ...seo }); toast('SEO 设置已保存。') } catch (e) { if (e instanceof AdminError) { errors.value = e.fields; toastError(e.firstField ? `${e.message}（${e.firstField}）` : e.message) } else toastError('保存没有成功。') } finally { busy.value = false }
}

/* ---- redirects ---- */
const rq = ref('')
const rsort = ref<'new' | 'hits'>('new')
const rpage = ref(1)
const list = ref<ListPage<RedirectRow> | null>(null)
const editing = ref<RedirectRow | 'new' | null>(null)
const form = reactive({ source: '', target: '', status_code: 301 as 301 | 302 })
const { busy: rbusy, fields, run } = useSubmit()
async function loadRedirects(): Promise<void> { try { list.value = await api.get<ListPage<RedirectRow>>('/redirects', { q: rq.value.trim(), sort: rsort.value, page: rpage.value, per: 30 }) } catch (e) { toastError(e instanceof AdminError ? e.message : '重定向加载失败。') } }
onMounted(loadRedirects)
watch([rsort, rpage], loadRedirects)
const search = debounced(() => { rpage.value = 1; void loadRedirects() }, 350)
function open(r: RedirectRow | 'new'): void { editing.value = r; Object.assign(form, r === 'new' ? { source: '', target: '', status_code: 301 } : { source: r.source, target: r.target, status_code: r.status_code }) }
async function saveRedirect(): Promise<void> {
  const t = editing.value
  try { await run(async () => { if (t === 'new') await api.post('/redirects', { ...form }); else if (t) await api.patch(`/redirects/${t.id}`, { ...form }) }); toast('重定向已保存。'); editing.value = null; await loadRedirects() } catch (e) { if (!(e instanceof AdminError && e.status === 422)) toastError(e instanceof AdminError ? e.message : '保存没有成功。') }
}
async function removeRedirect(r: RedirectRow): Promise<void> {
  if (!(await confirm({ title: '删除这条重定向？', text: `${r.source} → ${r.target}。之后访问 ${r.source} 会变成 404（如果那里没有内容）。`, confirm: '删除', danger: true }))) return
  try { await api.del(`/redirects/${r.id}`); toast('已删除。'); await loadRedirects() } catch (e) { toastError(e instanceof AdminError ? e.message : '删除没有成功。') }
}
const codeOptions = [{ value: 301, label: '301 永久' }, { value: 302, label: '302 临时' }]
</script>

<template>
  <div>
    <PageHead title="SEO" sub="搜索引擎、分享卡片、站点地图，以及旧地址的重定向。" />
    <p v-if="!loaded" class="adm-boot" role="status">正在加载设置……</p>
    <div v-else class="adm-stack">
      <form class="adm-card adm-section" @submit.prevent="saveSeo">
        <h2>搜索与分享</h2>
        <div class="adm-form adm-form--2">
          <Field v-slot="{ id }" label="默认标题" :error="errors.title" hint="留空用“站点名 · 副标题”"><input :id="id" v-model="seo.title" class="input" maxlength="120"></Field>
          <Field label="默认分享图" hint="文章没有自己的分享图和封面时用它"><MediaField v-model="seo.share_image_media_id" title="选择分享图" /></Field>
          <Field label="规范域名" class="span-2" hint="所有绝对链接（站点地图、分享卡片）都用它。它写在服务器的环境变量 BLOG_SITE_URL 里，改完要重启服务，所以这里只读。"><p class="adm-readonly adm-mono">{{ origin || '（未设置）' }}</p></Field>
          <Field v-slot="{ id }" label="默认描述" class="span-2" :error="errors.description" hint="留空用站点描述"><textarea :id="id" v-model="seo.description" class="textarea" rows="2" maxlength="300" /></Field>
          <Field label="关键词" class="span-2" :error="errors.keywords" hint="可选，最多 15 个。现在的搜索引擎基本不看它了。"><TagInput v-model="seo.keywords" :max="15" label="关键词" /></Field>
        </div>
        <h2 class="adm-section__sub">站点地图</h2>
        <div class="adm-form adm-form--2">
          <div class="adm-switches span-2">
            <SwitchField v-model="seo.sitemap.moments" label="动态进站点地图" /><SwitchField v-model="seo.sitemap.pages" label="独立页面进站点地图" /><SwitchField v-model="seo.sitemap.taxonomy" label="分类、标签、系列进站点地图" />
          </div>
        </div>
        <h2 class="adm-section__sub">robots.txt 追加的规则</h2>
        <Field v-slot="{ id }" label="每行一条" :error="errors.robots_extra" hint="只接受 User-agent / Allow / Disallow / Crawl-delay 和 # 注释。默认已经禁止抓取 /api/ 和 /admin。">
          <textarea :id="id" v-model="seo.robots_extra" class="textarea adm-mono-area" rows="4" spellcheck="false" placeholder="Disallow: /archive" />
        </Field>
        <div class="adm-section__foot"><a class="btn btn--ghost" href="/robots.txt" target="_blank" rel="noopener"><AIcon name="external" />看 robots.txt</a><a class="btn btn--ghost" href="/sitemap.xml" target="_blank" rel="noopener"><AIcon name="external" />看站点地图</a><button class="btn btn--fill" type="submit" :disabled="busy"><AIcon name="a-save" />保存</button></div>
      </form>

      <section class="adm-card adm-section" aria-labelledby="redir-h">
        <h2 id="redir-h">重定向</h2>
        <p class="adm-hint">改文章、页面、分类的别名时，旧地址会自动在这里留一条 301。也可以手动加：站内旧路径 → 站内新路径或完整链接。</p>
        <div class="adm-toolbar">
          <div class="searchfield"><AIcon name="search" /><input v-model="rq" class="input" type="search" placeholder="搜来源或目标" aria-label="搜索重定向" @input="search()"></div>
          <select v-model="rsort" class="select" aria-label="排序"><option value="new">最新</option><option value="hits">命中最多</option></select>
          <span class="adm-toolbar__grow" />
          <button class="btn btn--sm btn--fill" type="button" @click="open('new')"><AIcon name="a-plus" />加一条</button>
        </div>
        <EmptyBox v-if="list && !list.items.length" title="还没有重定向" text="改过别名，或者手动加一条，这里就有了。" />
        <TableWrap v-else-if="list" label="重定向列表">
          <table class="adm-table">
            <thead><tr><th>来源</th><th>目标</th><th>类型</th><th class="is-num">命中</th><th class="is-nowrap">最近命中</th><th class="is-shrink"><span class="sr-only">操作</span></th></tr></thead>
            <tbody>
              <tr v-for="r in list.items" :key="r.id">
                <td class="adm-mono">{{ r.source }}</td><td class="adm-mono">{{ r.target }}</td>
                <td><span class="adm-badge">{{ r.status_code }}</span><span v-if="r.auto" class="adm-badge adm-badge--ok">自动</span></td>
                <td class="is-num">{{ r.hits }}</td><td class="is-nowrap">{{ r.last_hit_at ? ago(r.last_hit_at) : '—' }}</td>
                <td class="is-nowrap"><button class="btn btn--sm btn--ghost" type="button" @click="open(r)"><AIcon name="a-edit" />编辑</button><button class="icon-btn icon-btn--ghost" type="button" :aria-label="`删除 ${r.source}`" @click="removeRedirect(r)"><AIcon name="a-trash" /></button></td>
              </tr>
            </tbody>
          </table>
        </TableWrap>
        <Pagination v-if="list" :page="list.page" :pages="list.pages" @go="(n) => (rpage = n)" />
      </section>
    </div>

    <Modal :open="editing !== null" :title="editing === 'new' ? '新建重定向' : '编辑重定向'" @close="editing = null">
      <form class="adm-form" @submit.prevent="saveRedirect">
        <Field v-slot="{ id }" label="来源（站内路径）" required :error="fields.source" hint="例如 /blog/old-slug"><input :id="id" v-model="form.source" class="input" spellcheck="false" placeholder="/blog/old-slug" data-autofocus></Field>
        <Field v-slot="{ id }" label="目标" required :error="fields.target" hint="站内路径，或完整的 https:// 链接"><input :id="id" v-model="form.target" class="input" spellcheck="false" placeholder="/blog/new-slug"></Field>
        <Field label="类型" hint="301 = 搬家了（搜索引擎会更新），302 = 暂时的"><Segmented v-model="form.status_code" label="重定向类型" :options="codeOptions" /></Field>
      </form>
      <template #footer><button class="btn btn--ghost" type="button" @click="editing = null">取消</button><button class="btn btn--fill" type="button" :disabled="rbusy || !form.source || !form.target" @click="saveRedirect">保存</button></template>
    </Modal>
  </div>
</template>
