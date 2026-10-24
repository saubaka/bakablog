<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { copyText } from '@/shared/clipboard'
import type { Media } from '@/shared/types'
import { api, AdminError } from '../api/client'
import { uploadMedia } from '../api/media'
import { afterSave } from '../editor/save-state'
import CoverPicker from '../editor/CoverPicker.vue'
import MarkdownEditor from '../editor/MarkdownEditor.vue'
import PreviewPane from '../editor/PreviewPane.vue'
import RevisionDrawer from '../editor/RevisionDrawer.vue'
import { ago, fromLocalInput, toLocalInput, when } from '../format'
import { loadTaxonomy, taxo } from '../taxonomy'
import type { AdminMedia, AdminPost, CardStyle, PostInput, PostStatus } from '../types'
import AIcon from '../ui/AIcon'
import { confirm } from '../ui/confirm'
import Field from '../ui/Field.vue'
import MediaPicker from '../ui/MediaPicker.vue'
import Segmented from '../ui/Segmented.vue'
import SwitchField from '../ui/SwitchField.vue'
import TagInput from '../ui/TagInput.vue'
import { toast, toastError } from '../ui/toast'
import { debounced, useLeaveGuard } from '../use'

interface Form {
  title: string; slug: string; summary: string; content_md: string; status: PostStatus; published_at: string; pinned: boolean; featured: boolean
  category_id: number | null; tags: string[]; series_id: number | null; series_order: number | null
  cover: Media | null; cover_alt: string; cover_focus_x: number; cover_focus_y: number; card_style: CardStyle
  show_toc: boolean; show_reading_time: boolean; show_author_card: boolean
  seo_title: string; seo_description: string; seo_image: Media | null; canonical_url: string
}
const blank = (): Form => ({
  title: '', slug: '', summary: '', content_md: '', status: 'draft', published_at: '', pinned: false, featured: false, category_id: null, tags: [], series_id: null, series_order: null,
  cover: null, cover_alt: '', cover_focus_x: 50, cover_focus_y: 50, card_style: 'auto', show_toc: true, show_reading_time: true, show_author_card: false,
  seo_title: '', seo_description: '', seo_image: null, canonical_url: '',
})
const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v)) as T

const route = useRoute()
const router = useRouter()
const form = reactive<Form>(blank())
const saved = ref<Form>(blank())
const postId = ref<number | null>(null)
const updatedAt = ref('')
const savedStatus = ref<PostStatus>('draft')
const deletedAt = ref<string | null>(null)
const loading = ref(false)
const loadError = ref('')
const saving = ref(false)
const autosavedAt = ref('')
const fieldErrors = ref<Record<string, string>>({})
const tab = ref<'write' | 'preview' | 'settings'>('write')
const historyOpen = ref(false)
const settingsOpen = ref(false)
const pickerFor = ref<'' | 'one' | 'gallery'>('')
const editor = ref<InstanceType<typeof MarkdownEditor> | null>(null)
const preview = ref<InstanceType<typeof PreviewPane> | null>(null)
const slugTouched = ref(false)
const stats = ref({ words: 0, minutes: 0 })
const autosaveFound = ref<AdminPost['autosave']>(null)

const dirty = computed(() => JSON.stringify(form) !== JSON.stringify(saved.value))
let generation = 0
let acceptingFirstSave = false
useLeaveGuard(() => dirty.value && !acceptingFirstSave, undefined, true)
onBeforeUnmount(() => { generation++; makeSlug.cancel() })

/* ---- loading ---- */
function apply(p: AdminPost, submitted?: Form): void {
  const next: Form = {
    title: p.title, slug: p.slug, summary: p.summary_auto ? '' : p.summary, content_md: p.content_md, status: p.status, published_at: toLocalInput(p.published_at), pinned: p.pinned, featured: p.featured,
    category_id: p.category_id, tags: p.tags.map((t) => t.name), series_id: p.series_id, series_order: p.series_order, cover: p.cover, cover_alt: p.cover_alt,
    cover_focus_x: p.cover_focus?.x ?? 50, cover_focus_y: p.cover_focus?.y ?? 50, card_style: p.card_style, show_toc: p.show_toc, show_reading_time: p.show_reading_time,
    show_author_card: p.show_author_card, seo_title: p.seo.title, seo_description: p.seo.description, seo_image: p.seo.image, canonical_url: p.seo.canonical_url,
  }
  Object.assign(form, clone(submitted ? afterSave(form, submitted, next) : next))
  saved.value = clone(next)
  postId.value = p.id
  updatedAt.value = p.updated_at
  savedStatus.value = p.status
  deletedAt.value = p.deleted_at
  slugTouched.value = true
  autosaveFound.value = p.autosave
  stats.value = { words: p.word_count, minutes: p.reading_minutes }
}

function reset(): void {
  generation++
  makeSlug.cancel()
  Object.assign(form, blank())
  saved.value = blank()
  postId.value = null
  updatedAt.value = ''
  loadError.value = ''
  loading.value = false
  saving.value = false
  slugTouched.value = false
  tab.value = 'write'
  historyOpen.value = false
  fieldErrors.value = {}
  savedStatus.value = 'draft'
  deletedAt.value = null
  autosavedAt.value = ''
  autosaveFound.value = null
  settingsOpen.value = false
  pickerFor.value = ''
  stats.value = { words: 0, minutes: 0 }
  window.clearTimeout(idle)
}
async function load(id: number): Promise<void> {
  const mine = generation
  loading.value = true
  try {
    const result = await api.get<AdminPost>(`/posts/${id}`)
    if (mine === generation) apply(result)
  } catch (e) {
    if (mine === generation) loadError.value = e instanceof AdminError ? e.message : '文章加载失败。'
  } finally { if (mine === generation) loading.value = false }
}
onMounted(() => { void loadTaxonomy() })
/* ---- the body of a save: only what changed ---- */
function body(): PostInput {
  const f = form
  const s = saved.value
  const out: PostInput = {}
  const same = (a: unknown, b: unknown): boolean => JSON.stringify(a) === JSON.stringify(b)
  if (!postId.value || f.title !== s.title) out.title = f.title
  if (f.slug && (!postId.value || f.slug !== s.slug)) out.slug = f.slug
  if (!postId.value || f.summary !== s.summary) out.summary = f.summary
  if (!postId.value || f.content_md !== s.content_md) out.content_md = f.content_md
  if (!postId.value || f.status !== s.status) out.status = f.status
  if (!postId.value || f.published_at !== s.published_at) out.published_at = fromLocalInput(f.published_at)
  if (!postId.value || f.pinned !== s.pinned) out.pinned = f.pinned
  if (!postId.value || f.featured !== s.featured) out.featured = f.featured
  if (!postId.value || f.category_id !== s.category_id) out.category_id = f.category_id
  if (!postId.value || !same(f.tags, s.tags)) out.tags = f.tags
  if (!postId.value || f.series_id !== s.series_id) out.series_id = f.series_id
  if (f.series_id && (!postId.value || f.series_order !== s.series_order) && f.series_order) out.series_order = f.series_order
  if (!postId.value || f.cover?.id !== s.cover?.id) out.cover_media_id = f.cover?.id ?? null
  if (!postId.value || f.cover_alt !== s.cover_alt) out.cover_alt = f.cover_alt
  if (!postId.value || f.cover_focus_x !== s.cover_focus_x) out.cover_focus_x = f.cover_focus_x
  if (!postId.value || f.cover_focus_y !== s.cover_focus_y) out.cover_focus_y = f.cover_focus_y
  if (!postId.value || f.card_style !== s.card_style) out.card_style = f.card_style
  if (!postId.value || f.show_toc !== s.show_toc) out.show_toc = f.show_toc
  if (!postId.value || f.show_reading_time !== s.show_reading_time) out.show_reading_time = f.show_reading_time
  if (!postId.value || f.show_author_card !== s.show_author_card) out.show_author_card = f.show_author_card
  if (!postId.value || f.seo_title !== s.seo_title) out.seo_title = f.seo_title
  if (!postId.value || f.seo_description !== s.seo_description) out.seo_description = f.seo_description
  if (!postId.value || f.seo_image?.id !== s.seo_image?.id) out.seo_image_media_id = f.seo_image?.id ?? null
  if (!postId.value || f.canonical_url !== s.canonical_url) out.canonical_url = f.canonical_url
  return out
}

async function save(opts: { publish?: boolean; quiet?: boolean; force?: boolean } = {}): Promise<boolean> {
  if (saving.value) return false
  if (!form.title.trim()) { fieldErrors.value = { title: '先写个标题' }; toastError('先写个标题。'); return false }
  if (opts.publish && form.status === 'draft') form.status = 'published'
  saving.value = true
  fieldErrors.value = {}
  const mine = generation
  const submitted = clone(form)
  try {
    const payload = body()
    const post = postId.value
      ? await api.patch<AdminPost>(`/posts/${postId.value}`, { ...payload, ...(opts.force ? {} : { expected_updated_at: updatedAt.value }) })
      : await api.post<AdminPost>('/posts', payload)
    if (mine !== generation) return false
    const first = !postId.value
    apply(post, submitted)
    if (!opts.quiet) toast(post.status === 'published' ? (post.scheduled ? `已设为定时发布（${when(post.published_at)}）。` : '已保存并发布。') : '已保存。')
    if (first) {
      acceptingFirstSave = true
      try { await router.replace(`/posts/${post.id}`) } finally { acceptingFirstSave = false }
    }
    await loadTaxonomy(true)
    return true
  } catch (e) {
    if (mine !== generation) return false
    if (e instanceof AdminError && e.conflict && e.code === 'conflict') {
      const ok = await confirm({ title: '这篇文章在别处被改过了', text: '另一个窗口或设备保存过它。要用你现在的内容覆盖吗？（覆盖前，对方那一版仍在“版本历史”里。）', confirm: '用我的覆盖', cancel: '先不', danger: true })
      if (ok) { saving.value = false; return await save({ ...opts, force: true }) }
    } else if (e instanceof AdminError) {
      fieldErrors.value = e.fields
      toastError(e.firstField ? `${e.message}（${e.firstField}）` : e.message)
    } else toastError('保存没有成功，请再试一次。')
    return false
  } finally {
    if (mine === generation) saving.value = false
  }
}

/* ---- the title makes the slug (until the author types one) ---- */
const makeSlug = debounced(async () => {
  if (slugTouched.value || !form.title.trim() || postId.value) return
  const mine = generation
  const title = form.title
  try {
    const result = await api.post<{ slug: string }>('/utils/slug', { title, kind: 'post' })
    if (mine === generation && form.title === title && !slugTouched.value && !postId.value) form.slug = result.slug
  } catch { /* the server makes one when saving */ }
}, 600)
watch(() => form.title, () => makeSlug())

/* ---- autosave: a pause of ten seconds keeps the text aside on the server ---- */
let idle = 0
watch(() => [form.title, form.summary, form.content_md, form.tags.join('\u0001')], () => {
  window.clearTimeout(idle)
  idle = window.setTimeout(() => void autosave(), 10_000)
})
async function autosave(): Promise<void> {
  if (!dirty.value || saving.value) return
  const mine = generation
  try {
    if (!postId.value) {
      if (!form.title.trim()) return
      await save({ quiet: true })             // a new text becomes a draft on the server, so nothing typed is ever only in this tab
      if (mine === generation) autosavedAt.value = new Date().toISOString()
      return
    }
    await api.put(`/posts/${postId.value}/autosave`, { title: form.title, summary: form.summary, content_md: form.content_md, tags: form.tags })
    if (mine === generation) autosavedAt.value = new Date().toISOString()
  } catch { /* the next pause tries again; the page stays usable */ }
}
onBeforeUnmount(() => window.clearTimeout(idle))

watch(() => route.params.id, (v) => {
  const id = Number(v)
  if (id && id === postId.value) return // first save keeps the current editor and its newer input
  reset()
  if (id) void load(id)
}, { immediate: true })

function restoreAutosave(): void {
  const a = autosaveFound.value
  if (!a) return
  const s = a.snapshot
  if (s.title !== undefined) form.title = s.title
  if (s.summary !== undefined) form.summary = s.summary
  if (s.content_md !== undefined) form.content_md = s.content_md
  if (s.tags) form.tags = s.tags
  autosaveFound.value = null
  toast('已恢复暂存的内容，记得保存。')
}

/* ---- pictures ---- */
const upload = async (file: File): Promise<{ id: number; alt: string }> => { const m = await uploadMedia(file); return { id: m.id, alt: m.alt || m.filename.replace(/\.[a-z0-9]+$/i, '') } }
function onPick(items: AdminMedia[]): void {
  editor.value?.insertImages(items.map((m) => ({ id: m.id, alt: m.alt || m.filename.replace(/\.[a-z0-9]+$/i, '') })))
  pickerFor.value = ''
}

/* ---- status and publishing ---- */
const statusOptions = [{ value: 'draft', label: '草稿' }, { value: 'published', label: '已发布' }, { value: 'unlisted', label: '仅链接可见', hint: '知道链接的人能看，但不会出现在列表、搜索和订阅里' }, { value: 'private', label: '私密', hint: '只有登录后台的你能看' }]
const cardOptions = [{ value: 'auto', label: '自动' }, { value: 'cover', label: '封面卡' }, { value: 'side', label: '左图右文' }, { value: 'note', label: '便签' }, { value: 'quote', label: '引言' }]
const scheduled = computed(() => form.status === 'published' && !!form.published_at && new Date(form.published_at).getTime() > Date.now())
const primaryLabel = computed(() => (savedStatus.value === 'published' ? '更新' : form.status === 'published' ? (scheduled.value ? '定时发布' : '发布') : '发布'))

async function previewLink(): Promise<void> {
  if (!postId.value) { if (!(await save())) return }
  try {
    const r = await api.post<{ path: string; url: string }>(`/posts/${postId.value}/preview-token`)
    toast((await copyText(r.url)) ? '预览链接已复制（7 天内有效）。' : '预览链接已生成。')
    window.open(r.path, '_blank', 'noopener')
  } catch (e) { toastError(e instanceof AdminError ? e.message : '生成预览链接失败。') }
}
async function trash(): Promise<void> {
  if (!postId.value) return
  if (!(await confirm({ title: '移入回收站？', text: '文章会从前台消失，30 天内可以在回收站恢复。', confirm: '移入回收站', danger: true }))) return
  try { await api.del(`/posts/${postId.value}`); saved.value = clone(form); toast('已移入回收站。'); await router.replace('/posts') } catch (e) { toastError(e instanceof AdminError ? e.message : '没有成功。') }
}
async function restoreRevision(id: number): Promise<void> {
  if (!postId.value) return
  if (dirty.value && !(await confirm({ title: '恢复到这个版本？', text: '编辑器里还没保存的改动会被替换。', confirm: '恢复', danger: true }))) return
  try { apply(await api.post<AdminPost>(`/posts/${postId.value}/revisions/${id}/restore`)); historyOpen.value = false; toast('已恢复到那个版本。') } catch (e) { toastError(e instanceof AdminError ? e.message : '恢复没有成功。') }
}
async function restoreFromTrash(): Promise<void> {
  if (!postId.value) return
  try { apply(await api.post<AdminPost>(`/posts/${postId.value}/restore`)); toast('已从回收站恢复。') } catch (e) { toastError(e instanceof AdminError ? e.message : '恢复没有成功。') }
}

const state = computed(() => {
  if (saving.value) return '正在保存……'
  if (dirty.value) return '有还没保存的改动'
  if (autosavedAt.value && !dirty.value) return `已保存`
  return postId.value ? `已保存 · 修改于 ${ago(updatedAt.value)}` : '新文章'
})

function onKey(e: KeyboardEvent): void { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') { e.preventDefault(); void save() } }
onMounted(() => document.addEventListener('keydown', onKey))
onBeforeUnmount(() => document.removeEventListener('keydown', onKey))

let syncing = false
function fromEditor(r: number): void { if (syncing) return; syncing = true; preview.value?.setScroll(r); requestAnimationFrame(() => { syncing = false }) }
</script>

<template>
  <div class="adm-editor">
    <p v-if="loadError" class="adm-error" role="alert">{{ loadError }} <RouterLink class="text-link" to="/posts">回到文章列表</RouterLink></p>
    <template v-else>
      <h1 class="sr-only">{{ postId ? '编辑文章' : '写文章' }}</h1>
      <header class="adm-editor__bar">
        <RouterLink class="text-link" to="/posts"><AIcon name="arrow-l" />文章</RouterLink>
        <span class="adm-editor__state" :class="{ 'is-dirty': dirty }" role="status">{{ state }}</span>
        <span class="adm-toolbar__grow" />
        <button class="btn btn--ghost btn--sm adm-editor__settings-btn" type="button" :aria-expanded="settingsOpen" aria-controls="adm-editor-side" @click="settingsOpen = !settingsOpen"><AIcon name="a-settings" />设置</button>
        <button v-if="postId" class="btn btn--ghost btn--sm" type="button" @click="historyOpen = true"><AIcon name="a-history" />版本</button>
        <button class="btn btn--ghost btn--sm" type="button" @click="previewLink"><AIcon name="a-eye" />预览</button>
        <button class="btn btn--sm" type="button" :disabled="saving || (!dirty && !!postId)" @click="save()"><AIcon name="a-save" />保存</button>
        <button class="btn btn--sm btn--fill" type="button" :disabled="saving || (!dirty && savedStatus === 'published')" @click="save({ publish: true })">{{ primaryLabel }}</button>
      </header>

      <p v-if="deletedAt" class="adm-error">这篇文章在回收站里。<button class="text-link" type="button" @click="restoreFromTrash">恢复它</button></p>
      <p v-if="autosaveFound" class="adm-note" role="status">发现一份 {{ when(autosaveFound.saved_at) }} 的暂存内容，比已保存的更新。<button class="text-link" type="button" @click="restoreAutosave">恢复暂存</button> · <button class="text-link" type="button" @click="autosaveFound = null">忽略</button></p>

      <div class="adm-tabs adm-editor__tabs" role="tablist" aria-label="编辑区域">
        <button class="tab" type="button" role="tab" :aria-selected="tab === 'write'" @click="tab = 'write'">写</button>
        <button class="tab" type="button" role="tab" :aria-selected="tab === 'preview'" @click="tab = 'preview'">预览</button>
        <button class="tab" type="button" role="tab" :aria-selected="tab === 'settings'" @click="tab = 'settings'">设置</button>
      </div>

      <div class="adm-editor__grid" :data-tab="tab">
        <section class="adm-editor__main" aria-label="正文">
          <Field v-slot="{ id, invalid }" label="标题" :error="fieldErrors.title">
            <input :id="id" v-model="form.title" class="input adm-editor__title" :aria-invalid="invalid" placeholder="文章标题" autocomplete="off" maxlength="200">
          </Field>
          <Field v-slot="{ id }" label="别名（网址的一部分）" :error="fieldErrors.slug" :hint="postId && savedStatus !== 'draft' ? '改了别名，旧地址会自动 301 跳到新地址。' : '用来生成 /blog/别名；中文标题会转成拼音，可以手改。'">
            <div class="adm-slug"><span>/blog/</span><input :id="id" v-model="form.slug" class="input" autocomplete="off" spellcheck="false" @input="slugTouched = true"></div>
          </Field>
          <div class="adm-editor__panes">
            <div class="adm-editor__pane adm-editor__pane--write">
              <MarkdownEditor ref="editor" v-model="form.content_md" :upload="upload" placeholder="用 Markdown 写。可以粘贴或拖进图片；:::tip 标题 … ::: 是提示块。" @pick-image="(m) => (pickerFor = m)" @save="save()" @scroll="fromEditor" />
            </div>
            <div class="adm-editor__pane adm-editor__pane--preview"><PreviewPane ref="preview" :markdown="form.content_md" @result="(r) => (stats = { words: r.words, minutes: r.minutes })" /></div>
          </div>
          <p class="adm-editor__count">{{ stats.words }} 字 · 约 {{ stats.minutes }} 分钟读完</p>
          <Field v-slot="{ id }" label="摘要" hint="留空时，自动截取正文开头约 120 字。">
            <textarea :id="id" v-model="form.summary" class="textarea" rows="3" maxlength="1000" placeholder="（自动）" />
          </Field>
        </section>

        <aside id="adm-editor-side" class="adm-editor__side" :class="{ 'is-open': settingsOpen }" aria-label="文章设置">
          <button class="icon-btn icon-btn--ghost adm-editor__side-x" type="button" aria-label="关闭设置" @click="settingsOpen = false"><AIcon name="close" /></button>
          <section class="adm-card adm-panel">
            <h2>发布</h2>
            <Segmented v-model="form.status" label="状态" :options="statusOptions" />
            <Field v-slot="{ id }" label="发布时间" hint="留空 = 保存时的现在。选一个将来的时间，就是定时发布。">
              <input :id="id" v-model="form.published_at" class="input" type="datetime-local">
            </Field>
            <p v-if="scheduled" class="adm-badge adm-badge--rose">定时：{{ when(fromLocalInput(form.published_at)) }} 自动发布</p>
            <SwitchField v-model="form.pinned" label="置顶" hint="在列表最前面，卡片上有“置顶”标记" />
            <SwitchField v-model="form.featured" label="精选" hint="可以出现在首页的“精选”模块" />
            <button v-if="postId && !deletedAt" class="btn btn--sm btn--danger" type="button" @click="trash"><AIcon name="a-trash" />移入回收站</button>
          </section>

          <section class="adm-card adm-panel">
            <h2>整理</h2>
            <Field v-slot="{ id }" label="分类"><select :id="id" v-model="form.category_id" class="select"><option :value="null">（没有分类）</option><option v-for="c in taxo.categories" :key="c.id" :value="c.id">{{ c.name }}</option></select></Field>
            <Field label="标签" hint="没有的标签会在保存时自动新建。"><TagInput v-model="form.tags" :suggestions="taxo.tags.map((t) => t.name)" /></Field>
            <Field v-slot="{ id }" label="系列"><select :id="id" v-model="form.series_id" class="select"><option :value="null">（不属于系列）</option><option v-for="s in taxo.series" :key="s.id" :value="s.id">{{ s.title }}</option></select></Field>
            <Field v-if="form.series_id" v-slot="{ id }" label="第几篇" hint="留空放在最后。系列页里可以拖拽调整。"><input :id="id" v-model.number="form.series_order" class="input" type="number" min="1" inputmode="numeric"></Field>
          </section>

          <section class="adm-card adm-panel">
            <h2>封面</h2>
            <CoverPicker :media="form.cover" :alt="form.cover_alt" :focus-x="form.cover_focus_x" :focus-y="form.cover_focus_y" with-focus with-alt title="选择封面"
              @pick="(m) => (form.cover = m)" @update:alt="(v) => (form.cover_alt = v)" @update:focus="(x, y) => { form.cover_focus_x = x; form.cover_focus_y = y }" />
            <p v-if="!form.cover" class="adm-hint">没有封面时，卡片会用标题生成一个浅色图案。</p>
          </section>

          <section class="adm-card adm-panel">
            <h2>样式</h2>
            <Field label="列表里的卡片"><Segmented v-model="form.card_style" label="卡片样式" :options="cardOptions" /></Field>
            <SwitchField v-model="form.show_toc" label="显示目录" />
            <SwitchField v-model="form.show_reading_time" label="显示阅读时间" />
            <SwitchField v-model="form.show_author_card" label="文末显示作者小卡片" />
          </section>

          <section class="adm-card adm-panel">
            <h2>搜索引擎与分享</h2>
            <Field v-slot="{ id }" label="标题" hint="留空用文章标题"><input :id="id" v-model="form.seo_title" class="input" maxlength="200"></Field>
            <Field v-slot="{ id }" label="描述" hint="留空用摘要"><textarea :id="id" v-model="form.seo_description" class="textarea" rows="2" maxlength="400" /></Field>
            <Field label="分享图" hint="留空用封面"><CoverPicker :media="form.seo_image" title="选择分享图" @pick="(m) => (form.seo_image = m)" /></Field>
            <Field v-slot="{ id }" label="规范链接" :error="fieldErrors.canonical_url" hint="转载自别处时，填原文地址（完整的 https:// 链接）"><input :id="id" v-model="form.canonical_url" class="input" type="url" placeholder="https://"></Field>
          </section>
        </aside>
      </div>

      <div class="scrim adm-editor__scrim" :class="{ 'is-open': settingsOpen }" @click="settingsOpen = false" />
      <MediaPicker :open="pickerFor !== ''" :multiple="pickerFor === 'gallery'" :title="pickerFor === 'gallery' ? '选择图集的图片' : '选择图片'" @close="pickerFor = ''" @pick="onPick" />
      <RevisionDrawer v-if="postId" :open="historyOpen" :base="`/posts/${postId}`" :current-markdown="form.content_md" :current-title="form.title" @close="historyOpen = false" @restore="restoreRevision" />
    </template>
    <p v-if="loading" class="adm-boot" role="status">正在打开文章……</p>
  </div>
</template>
