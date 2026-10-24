<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { copyText } from '@/shared/clipboard'
import { api, AdminError } from '../api/client'
import { ago, when } from '../format'
import { STATUS_LABEL } from '../labels'
import { loadTaxonomy, taxo } from '../taxonomy'
import AIcon from '../ui/AIcon'
import { confirm } from '../ui/confirm'
import EmptyBox from '../ui/EmptyBox.vue'
import Menu from '../ui/Menu.vue'
import Modal from '../ui/Modal.vue'
import TableWrap from '../ui/TableWrap.vue'
import PageHead from '../ui/PageHead.vue'
import Pagination from '../ui/Pagination.vue'
import TagInput from '../ui/TagInput.vue'
import { toast, toastError } from '../ui/toast'
import { debounced, useLoader, useRouteQuery } from '../use'
import type { AdminPostCard, PostList } from '../types'

const router = useRouter()
const { state, set } = useRouteQuery({ status: 'all', q: '', category: '', tag: '', series: '', month: '', sort: 'updated', page: '1' })
const view = ref<'table' | 'cards'>((() => { try { return localStorage.getItem('bb:admin-posts-view') === 'cards' ? 'cards' : 'table' } catch { return 'table' } })())
const selected = ref<Set<number>>(new Set())
const search = ref(state.value.q)
/** "2026-10" -> [first of the month, first of the next) in the browser's own time zone, as the API wants them (UTC instants) */
function monthRange(month: string): { from?: string; to?: string } {
  const m = /^(\d{4})-(\d{2})$/.exec(month)
  if (!m) return {}
  const y = Number(m[1]); const mo = Number(m[2])
  return { from: new Date(y, mo - 1, 1).toISOString(), to: new Date(y, mo, 1).toISOString() }
}
const { data, loading, error, reload } = useLoader((signal) => api.get<PostList>('/posts', {
  status: state.value.status, q: state.value.q, category: state.value.category, tag: state.value.tag, series: state.value.series, ...monthRange(state.value.month), sort: state.value.sort, page: state.value.page, per: 20,
}, signal), () => state.value)

onMounted(() => { void loadTaxonomy() })
watch(() => state.value.q, (v) => { search.value = v })
const applySearch = debounced((v: string) => set({ q: v.trim() }), 350)
watch(data, () => { selected.value = new Set() })
function setView(v: 'table' | 'cards'): void { view.value = v; try { localStorage.setItem('bb:admin-posts-view', v) } catch { /* optional */ } }

const tabs = computed(() => {
  const c = data.value?.counts
  return [
    { id: 'all', label: '全部', n: c?.all }, { id: 'draft', label: '草稿', n: c?.draft }, { id: 'published', label: '已发布', n: c?.published },
    { id: 'scheduled', label: '定时', n: c?.scheduled }, { id: 'unlisted', label: '仅链接可见', n: c?.unlisted }, { id: 'private', label: '私密', n: c?.private }, { id: 'trashed', label: '回收站', n: c?.trashed },
  ]
})
const trashView = computed(() => state.value.status === 'trashed')
const allChecked = computed(() => !!data.value?.items.length && data.value.items.every((p) => selected.value.has(p.id)))
function toggleAll(on: boolean): void { selected.value = on ? new Set(data.value?.items.map((p) => p.id) ?? []) : new Set() }
function toggle(id: number): void { const s = new Set(selected.value); if (s.has(id)) s.delete(id); else s.add(id); selected.value = s }
const statusText = (p: AdminPostCard): string => (p.deleted_at ? '回收站' : p.scheduled ? '定时' : (STATUS_LABEL[p.status] ?? p.status))
const statusClass = (p: AdminPostCard): string => (p.deleted_at ? 'adm-badge--mist' : p.status === 'published' && !p.scheduled ? 'adm-badge--ok' : p.status === 'draft' ? '' : 'adm-badge--rose')

/* ---- row actions ---- */
async function guarded(fn: () => Promise<unknown>, done: string): Promise<void> {
  try { await fn(); toast(done); await reload() } catch (e) { toastError(e instanceof AdminError ? e.message : '没有成功，请再试一次。') }
}
async function preview(p: AdminPostCard): Promise<void> {
  if (p.status === 'published' && !p.scheduled && !p.deleted_at) { window.open(p.url, '_blank', 'noopener'); return }
  try { const r = await api.post<{ path: string }>(`/posts/${p.id}/preview-token`); window.open(r.path, '_blank', 'noopener') } catch (e) { toastError(e instanceof AdminError ? e.message : '生成预览链接失败。') }
}
async function copyLink(p: AdminPostCard): Promise<void> { toast((await copyText(`${location.origin}${p.url}`)) ? '链接已复制。' : '复制失败，请手动复制。') }
const duplicate = (p: AdminPostCard) => guarded(async () => { const r = await api.post<{ id: number }>(`/posts/${p.id}/duplicate`); await router.push(`/posts/${r.id}`) }, '已复制为草稿。')
async function trash(p: AdminPostCard): Promise<void> {
  if (await confirm({ title: '移入回收站？', text: `「${p.title || '无标题'}」会从前台消失，30 天内可以在回收站恢复。`, confirm: '移入回收站', danger: true })) await guarded(() => api.del(`/posts/${p.id}`), '已移入回收站。')
}
const restore = (p: AdminPostCard) => guarded(() => api.post(`/posts/${p.id}/restore`), '已恢复。')
async function purge(p: AdminPostCard): Promise<void> {
  if (await confirm({ title: '永久删除？', text: `「${p.title || '无标题'}」会被彻底删除，不能再恢复。`, confirm: '永久删除', danger: true })) await guarded(() => api.del(`/posts/${p.id}/purge`), '已永久删除。')
}

/* ---- batch ---- */
const ids = computed(() => [...selected.value])
const batchModal = ref<'category' | 'add_tags' | 'remove_tags' | null>(null)
const batchCategory = ref<number | ''>('')
const batchTags = ref<string[]>([])
async function batch(action: string, extra: Record<string, unknown> = {}): Promise<void> {
  try {
    const r = await api.post<{ done: number }>('/posts/batch', { ids: ids.value, action, ...extra })
    toast(`已处理 ${r.done} 篇。`)
    batchModal.value = null
    await reload()
  } catch (e) { toastError(e instanceof AdminError ? e.message : '批量操作没有成功。') }
}
async function regenerateSummaries(): Promise<void> {
  if (await confirm({ title: `重新生成 ${ids.value.length} 篇的摘要？`, text: '摘要会改回“自动截取正文开头”。手写过的摘要会被替换，之后可以再改。', confirm: '重新生成' })) await batch('regenerate_summary')
}
async function batchTrash(): Promise<void> {
  if (await confirm({ title: `把 ${ids.value.length} 篇移入回收站？`, text: '它们会从前台消失，30 天内可以恢复。', confirm: '移入回收站', danger: true })) await batch('trash')
}
async function batchPurge(): Promise<void> {
  if (await confirm({ title: `永久删除 ${ids.value.length} 篇？`, text: '这些文章会被彻底删除，不能再恢复。', confirm: '永久删除', danger: true, typeToConfirm: '删除' })) await batch('purge')
}
</script>

<template>
  <div>
    <PageHead title="文章" sub="写过的、正在写的和还在排队的。">
      <RouterLink class="btn btn--fill" to="/posts/new"><AIcon name="a-edit" />写文章</RouterLink>
    </PageHead>

    <div class="adm-tabs" role="tablist" aria-label="文章状态">
      <button v-for="t in tabs" :key="t.id" class="tab" type="button" role="tab" :aria-selected="state.status === t.id" @click="set({ status: t.id })">{{ t.label }}<span v-if="t.n !== undefined" class="n">{{ t.n }}</span></button>
    </div>

    <div class="adm-toolbar">
      <div class="searchfield"><AIcon name="search" /><input v-model="search" class="input" type="search" placeholder="搜标题、摘要、正文……" aria-label="搜索文章" @input="applySearch(search)"></div>
      <select class="select" aria-label="分类" :value="state.category" @change="set({ category: ($event.target as HTMLSelectElement).value })"><option value="">所有分类</option><option v-for="c in taxo.categories" :key="c.id" :value="String(c.id)">{{ c.name }}</option></select>
      <select class="select" aria-label="标签" :value="state.tag" @change="set({ tag: ($event.target as HTMLSelectElement).value })"><option value="">所有标签</option><option v-for="t in taxo.tags" :key="t.id" :value="t.name">{{ t.name }}</option></select>
      <select class="select" aria-label="系列" :value="state.series" @change="set({ series: ($event.target as HTMLSelectElement).value })"><option value="">所有系列</option><option v-for="s in taxo.series" :key="s.id" :value="String(s.id)">{{ s.title }}</option></select>
      <input class="input adm-month" type="month" aria-label="发布月份" :value="state.month" @change="set({ month: ($event.target as HTMLInputElement).value })">
      <select class="select" aria-label="排序" :value="state.sort" @change="set({ sort: ($event.target as HTMLSelectElement).value })">
        <option value="updated">最近修改</option><option value="published">发布时间</option><option value="created">创建时间</option><option value="title">标题</option><option value="views">阅读量</option>
      </select>
      <span class="adm-toolbar__grow" />
      <div class="viewtoggle" role="group" aria-label="显示方式">
        <button type="button" :aria-pressed="view === 'table'" aria-label="表格" @click="setView('table')"><AIcon name="rows" /></button>
        <button type="button" :aria-pressed="view === 'cards'" aria-label="卡片" @click="setView('cards')"><AIcon name="grid" /></button>
      </div>
    </div>

    <div v-if="selected.size" class="adm-batch" role="region" aria-label="批量操作">
      <b>已选 {{ selected.size }} 篇</b>
      <template v-if="trashView">
        <button class="btn btn--sm" type="button" @click="batch('restore')">恢复</button>
        <button class="btn btn--sm btn--danger" type="button" @click="batchPurge">永久删除</button>
      </template>
      <template v-else>
        <button class="btn btn--sm" type="button" @click="batch('publish')">发布</button>
        <button class="btn btn--sm" type="button" @click="batch('draft')">转为草稿</button>
        <button class="btn btn--sm" type="button" @click="batchModal = 'category'">改分类</button>
        <button class="btn btn--sm" type="button" @click="batchTags = []; batchModal = 'add_tags'">加标签</button>
        <Menu label="更多" icon="more" align="start">
          <button role="menuitem" type="button" @click="batchTags = []; batchModal = 'remove_tags'">去掉标签</button>
          <button role="menuitem" type="button" @click="batch('pin')">置顶</button><button role="menuitem" type="button" @click="batch('unpin')">取消置顶</button>
          <button role="menuitem" type="button" @click="batch('feature')">设为精选</button><button role="menuitem" type="button" @click="batch('unfeature')">取消精选</button>
          <button role="menuitem" type="button" @click="regenerateSummaries">重新生成摘要</button>
        </Menu>
        <button class="btn btn--sm btn--danger" type="button" @click="batchTrash"><AIcon name="a-trash" />移入回收站</button>
      </template>
      <button class="btn btn--sm btn--ghost" type="button" @click="selected = new Set()">取消选择</button>
    </div>

    <p v-if="error" class="adm-error" role="alert">{{ error.message }} <button class="text-link" type="button" @click="reload">重试</button></p>
    <div v-else-if="loading && !data" class="adm-skel-grid" aria-busy="true"><span v-for="n in 5" :key="n" class="skel adm-skel adm-skel--row" /></div>

    <template v-if="data">
      <EmptyBox v-if="!data.items.length" :title="state.q || state.category || state.tag || state.series || state.month ? '没有符合条件的文章' : '这里还没有文章'" :text="state.status === 'all' && !state.q ? '写第一篇吧。' : '换个筛选条件试试。'">
        <RouterLink v-if="state.status === 'all' && !state.q" class="btn btn--fill btn--sm" to="/posts/new">写文章</RouterLink>
      </EmptyBox>

      <TableWrap v-else-if="view === 'table'" label="文章列表">
        <table class="adm-table">
          <thead><tr>
            <th class="is-shrink"><label class="check"><input type="checkbox" :checked="allChecked" aria-label="选择本页全部" @change="toggleAll(($event.target as HTMLInputElement).checked)"><span class="check__box"><AIcon name="check" /></span></label></th>
            <th>标题</th><th>状态</th><th>分类 / 标签</th><th class="is-nowrap">发布时间</th><th class="is-nowrap">修改</th><th class="is-num">阅读</th><th class="is-shrink"><span class="sr-only">操作</span></th>
          </tr></thead>
          <tbody>
            <tr v-for="p in data.items" :key="p.id">
              <td><label class="check"><input type="checkbox" :checked="selected.has(p.id)" :aria-label="`选择：${p.title}`" @change="toggle(p.id)"><span class="check__box"><AIcon name="check" /></span></label></td>
              <td class="adm-post__title">
                <RouterLink :to="`/posts/${p.id}`"><span class="adm-thumb"><img v-if="p.cover" :src="p.cover.variants[0]?.url ?? p.cover.src" :alt="''" width="56" height="40" loading="lazy"></span>
                  <span><b>{{ p.title || '（无标题）' }}</b><small>/{{ p.slug }}<template v-if="p.pinned"> · 置顶</template><template v-if="p.featured"> · 精选</template><template v-if="p.series"> · 系列「{{ p.series.title }}」第 {{ p.series.order }} 篇</template></small></span></RouterLink>
              </td>
              <td><span class="adm-badge" :class="statusClass(p)">{{ statusText(p) }}</span></td>
              <td><span v-if="p.category" class="tag tag--rose">{{ p.category.name }}</span><span v-for="t in p.tags.slice(0, 2)" :key="t.id" class="tag">{{ t.name }}</span><span v-if="p.tags.length > 2" class="adm-more-n">+{{ p.tags.length - 2 }}</span></td>
              <td class="is-nowrap"><time :datetime="p.published_at" :title="when(p.published_at)">{{ when(p.published_at).slice(0, 10) }}</time></td>
              <td class="is-nowrap"><time :datetime="p.updated_at" :title="when(p.updated_at)">{{ ago(p.updated_at) }}</time></td>
              <td class="is-num">{{ p.view_count }}</td>
              <td>
                <Menu :label="`「${p.title}」的操作`" icon="more" icon-only>
                  <template v-if="!p.deleted_at">
                    <RouterLink role="menuitem" :to="`/posts/${p.id}`"><AIcon name="a-edit" />编辑</RouterLink>
                    <button role="menuitem" type="button" @click="preview(p)"><AIcon name="a-eye" />预览</button>
                    <button role="menuitem" type="button" @click="copyLink(p)"><AIcon name="a-copy-link" />复制链接</button>
                    <button role="menuitem" type="button" @click="duplicate(p)"><AIcon name="copy" />复制为草稿</button>
                    <button role="menuitem" type="button" @click="trash(p)"><AIcon name="a-trash" />移入回收站</button>
                  </template>
                  <template v-else>
                    <button role="menuitem" type="button" @click="restore(p)"><AIcon name="a-undo" />恢复</button>
                    <button role="menuitem" type="button" @click="purge(p)"><AIcon name="a-trash" />永久删除</button>
                  </template>
                </Menu>
              </td>
            </tr>
          </tbody>
        </table>
      </TableWrap>

      <div v-else class="adm-cards">
        <article v-for="p in data.items" :key="p.id" class="adm-card adm-postcard">
          <label class="check adm-postcard__pick"><input type="checkbox" :checked="selected.has(p.id)" :aria-label="`选择：${p.title}`" @change="toggle(p.id)"><span class="check__box"><AIcon name="check" /></span></label>
          <RouterLink :to="`/posts/${p.id}`" class="adm-postcard__cover"><img v-if="p.cover" :src="p.cover.src" :alt="''" loading="lazy"></RouterLink>
          <div class="adm-postcard__body">
            <span class="adm-badge" :class="statusClass(p)">{{ statusText(p) }}</span>
            <h2><RouterLink :to="`/posts/${p.id}`">{{ p.title || '（无标题）' }}</RouterLink></h2>
            <p>{{ p.summary }}</p>
            <small>{{ when(p.published_at).slice(0, 10) }} · {{ p.view_count }} 次阅读 · 改于 {{ ago(p.updated_at) }}</small>
          </div>
        </article>
      </div>

      <Pagination :page="data.page" :pages="data.pages" @go="(n) => set({ page: String(n) }, { keepPage: true })" />
      <p class="adm-count">共 {{ data.total }} 篇</p>
    </template>

    <Modal :open="batchModal !== null" :title="batchModal === 'category' ? '改分类' : batchModal === 'add_tags' ? '加标签' : '去掉标签'" @close="batchModal = null">
      <label v-if="batchModal === 'category'" class="field"><span class="label">分类</span>
        <select v-model="batchCategory" class="select" data-autofocus><option value="">（不属于任何分类）</option><option v-for="c in taxo.categories" :key="c.id" :value="c.id">{{ c.name }}</option></select>
      </label>
      <div v-else class="field"><span class="label">标签</span><TagInput v-model="batchTags" :suggestions="taxo.tags.map((t) => t.name)" /></div>
      <template #footer>
        <button class="btn btn--ghost" type="button" @click="batchModal = null">取消</button>
        <button class="btn btn--fill" type="button" :disabled="batchModal !== 'category' && !batchTags.length" @click="batchModal === 'category' ? batch('category', { category_id: batchCategory === '' ? null : batchCategory }) : batch(batchModal ?? '', { tags: batchTags })">应用到 {{ selected.size }} 篇</button>
      </template>
    </Modal>
  </div>
</template>
