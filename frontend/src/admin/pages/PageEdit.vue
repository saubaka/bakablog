<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { Media } from '@/shared/types'
import { api, AdminError } from '../api/client'
import { uploadMedia } from '../api/media'
import { afterSave } from '../editor/save-state'
import CoverPicker from '../editor/CoverPicker.vue'
import MarkdownEditor from '../editor/MarkdownEditor.vue'
import PreviewPane from '../editor/PreviewPane.vue'
import RevisionDrawer from '../editor/RevisionDrawer.vue'
import { ago, fromLocalInput, toLocalInput } from '../format'
import type { AdminMedia, AdminPage, PostStatus } from '../types'
import AIcon from '../ui/AIcon'
import { confirm } from '../ui/confirm'
import Field from '../ui/Field.vue'
import MediaPicker from '../ui/MediaPicker.vue'
import Segmented from '../ui/Segmented.vue'
import SwitchField from '../ui/SwitchField.vue'
import { toast, toastError } from '../ui/toast'
import { debounced, useLeaveGuard } from '../use'

interface Form { title: string; slug: string; content_md: string; template: 'plain' | 'wide' | 'sidebar'; status: PostStatus; published_at: string; in_nav: boolean; in_footer: boolean; seo_title: string; seo_description: string; seo_image: Media | null }
const blank = (): Form => ({ title: '', slug: '', content_md: '', template: 'plain', status: 'published', published_at: '', in_nav: false, in_footer: false, seo_title: '', seo_description: '', seo_image: null })
const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v)) as T

const route = useRoute()
const router = useRouter()
const form = reactive<Form>(blank())
const saved = ref<Form>(blank())
const pageId = ref<number | null>(null)
const updatedAt = ref('')
const loadError = ref('')
const saving = ref(false)
const errors = ref<Record<string, string>>({})
const tab = ref<'write' | 'preview' | 'settings'>('write')
const historyOpen = ref(false)
const pickerOpen = ref(false)
const slugTouched = ref(false)
const editor = ref<InstanceType<typeof MarkdownEditor> | null>(null)
const preview = ref<InstanceType<typeof PreviewPane> | null>(null)
const url = ref('')
const dirty = computed(() => JSON.stringify(form) !== JSON.stringify(saved.value))
let generation = 0
let acceptingFirstSave = false
useLeaveGuard(() => dirty.value && !acceptingFirstSave, undefined, true)
onBeforeUnmount(() => { generation++; makeSlug.cancel() })

function apply(p: AdminPage, submitted?: Form): void {
  const next: Form = { title: p.title, slug: p.slug, content_md: p.content_md, template: p.template, status: p.status, published_at: toLocalInput((p as unknown as { published_at: string }).published_at), in_nav: p.in_nav, in_footer: p.in_footer, seo_title: p.seo.title, seo_description: p.seo.description, seo_image: p.seo.image }
  Object.assign(form, clone(submitted ? afterSave(form, submitted, next) : next))
  saved.value = clone(next)
  pageId.value = p.id
  updatedAt.value = p.updated_at
  url.value = p.url
  slugTouched.value = true
}
function reset(): void {
  generation++
  makeSlug.cancel()
  Object.assign(form, blank())
  saved.value = blank()
  pageId.value = null
  updatedAt.value = ''
  loadError.value = ''
  saving.value = false
  slugTouched.value = false
  tab.value = 'write'
  historyOpen.value = false
  errors.value = {}
  pickerOpen.value = false
  url.value = ''
}
async function load(id: number): Promise<void> {
  const mine = generation
  try {
    const result = await api.get<AdminPage>(`/pages/${id}`)
    if (mine === generation) apply(result)
  } catch (e) {
    if (mine === generation) loadError.value = e instanceof AdminError ? e.message : '页面加载失败。'
  }
}
const makeSlug = debounced(async () => {
  if (slugTouched.value || !form.title.trim() || pageId.value) return
  const mine = generation
  const title = form.title
  try {
    const result = await api.post<{ slug: string }>('/utils/slug', { title, kind: 'page' })
    if (mine === generation && form.title === title && !slugTouched.value && !pageId.value) form.slug = result.slug
  } catch { /* the server makes one */ }
}, 600)
watch(() => form.title, () => makeSlug())

watch(() => route.params.id, (v) => {
  const id = Number(v)
  if (id && id === pageId.value) return // first save keeps the current editor and its newer input
  reset()
  if (id) void load(id)
}, { immediate: true })

function body(): Record<string, unknown> {
  const f = form
  const s = saved.value
  const out: Record<string, unknown> = {}
  const all = !pageId.value
  if (all || f.title !== s.title) out.title = f.title
  if (f.slug && (all || f.slug !== s.slug)) out.slug = f.slug
  if (all || f.content_md !== s.content_md) out.content_md = f.content_md
  if (all || f.template !== s.template) out.template = f.template
  if (all || f.status !== s.status) out.status = f.status
  if (all || f.published_at !== s.published_at) out.published_at = fromLocalInput(f.published_at)
  if (all || f.in_nav !== s.in_nav) out.in_nav = f.in_nav
  if (all || f.in_footer !== s.in_footer) out.in_footer = f.in_footer
  if (all || f.seo_title !== s.seo_title) out.seo_title = f.seo_title
  if (all || f.seo_description !== s.seo_description) out.seo_description = f.seo_description
  if (all || f.seo_image?.id !== s.seo_image?.id) out.seo_image_media_id = f.seo_image?.id ?? null
  return out
}
async function save(force = false): Promise<void> {
  if (saving.value) return
  if (!form.title.trim()) { errors.value = { title: '先写个标题' }; toastError('先写个标题。'); return }
  saving.value = true
  errors.value = {}
  const mine = generation
  const submitted = clone(form)
  try {
    const payload = body()
    const first = !pageId.value
    const p = pageId.value ? await api.patch<AdminPage>(`/pages/${pageId.value}`, { ...payload, ...(force ? {} : { expected_updated_at: updatedAt.value }) }) : await api.post<AdminPage>('/pages', payload)
    if (mine !== generation) return
    apply(p, submitted)
    toast('页面已保存。')
    if (first) {
      acceptingFirstSave = true
      try { await router.replace(`/pages/${p.id}`) } finally { acceptingFirstSave = false }
    }
  } catch (e) {
    if (mine !== generation) return
    if (e instanceof AdminError && e.code === 'conflict') {
      if (await confirm({ title: '这个页面在别处被改过了', text: '要用你现在的内容覆盖吗？（对方那一版仍在“版本历史”里。）', confirm: '用我的覆盖', danger: true })) { saving.value = false; await save(true); return }
    } else if (e instanceof AdminError) { errors.value = e.fields; toastError(e.firstField ? `${e.message}（${e.firstField}）` : e.message) } else toastError('保存没有成功。')
  } finally { if (mine === generation) saving.value = false }
}
async function trash(): Promise<void> {
  if (!pageId.value) return
  if (!(await confirm({ title: '移入回收站？', text: '页面会从前台和导航里消失，30 天内可以恢复。', confirm: '移入回收站', danger: true }))) return
  try { await api.del(`/pages/${pageId.value}`); saved.value = clone(form); toast('已移入回收站。'); await router.replace('/pages') } catch (e) { toastError(e instanceof AdminError ? e.message : '没有成功。') }
}
async function restoreRevision(id: number): Promise<void> {
  if (!pageId.value) return
  if (dirty.value && !(await confirm({ title: '恢复到这个版本？', text: '编辑器里还没保存的改动会被替换。', confirm: '恢复', danger: true }))) return
  try { apply(await api.post<AdminPage>(`/pages/${pageId.value}/revisions/${id}/restore`)); historyOpen.value = false; toast('已恢复到那个版本。') } catch (e) { toastError(e instanceof AdminError ? e.message : '恢复没有成功。') }
}
const upload = async (file: File): Promise<{ id: number; alt: string }> => { const m = await uploadMedia(file); return { id: m.id, alt: m.alt || m.filename.replace(/\.[a-z0-9]+$/i, '') } }
const onPick = (items: AdminMedia[]): void => { editor.value?.insertImages(items.map((m) => ({ id: m.id, alt: m.alt || m.filename.replace(/\.[a-z0-9]+$/i, '') }))); pickerOpen.value = false }
function onKey(e: KeyboardEvent): void { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') { e.preventDefault(); void save() } }
onMounted(() => document.addEventListener('keydown', onKey))
onBeforeUnmount(() => document.removeEventListener('keydown', onKey))
const statusOptions = [{ value: 'published', label: '已发布' }, { value: 'draft', label: '草稿' }, { value: 'unlisted', label: '仅链接可见' }, { value: 'private', label: '私密' }]
const templateOptions = [{ value: 'plain', label: '纯文', hint: '阅读宽度的单栏，适合“关于”' }, { value: 'wide', label: '宽幅', hint: '更宽，适合友链、作品集' }, { value: 'sidebar', label: '带目录', hint: '长文，右侧有目录' }]
</script>

<template>
  <div class="adm-editor adm-editor--page">
    <p v-if="loadError" class="adm-error" role="alert">{{ loadError }} <RouterLink class="text-link" to="/pages">回到页面列表</RouterLink></p>
    <template v-else>
      <h1 class="sr-only">{{ pageId ? '编辑页面' : '新建页面' }}</h1>
      <header class="adm-editor__bar">
        <RouterLink class="text-link" to="/pages"><AIcon name="arrow-l" />页面</RouterLink>
        <span class="adm-editor__state" :class="{ 'is-dirty': dirty }" role="status">{{ saving ? '正在保存……' : dirty ? '有还没保存的改动' : pageId ? `已保存 · 修改于 ${ago(updatedAt)}` : '新页面' }}</span>
        <span class="adm-toolbar__grow" />
        <a v-if="pageId" class="btn btn--ghost btn--sm" :href="url" target="_blank" rel="noopener"><AIcon name="external" />在前台打开</a>
        <button v-if="pageId" class="btn btn--ghost btn--sm" type="button" @click="historyOpen = true"><AIcon name="a-history" />版本</button>
        <button class="btn btn--sm btn--fill" type="button" :disabled="saving || (!dirty && !!pageId)" @click="save()"><AIcon name="a-save" />保存</button>
      </header>
      <div class="adm-tabs adm-editor__tabs" role="tablist" aria-label="编辑区域">
        <button class="tab" type="button" role="tab" :aria-selected="tab === 'write'" @click="tab = 'write'">写</button>
        <button class="tab" type="button" role="tab" :aria-selected="tab === 'preview'" @click="tab = 'preview'">预览</button>
        <button class="tab" type="button" role="tab" :aria-selected="tab === 'settings'" @click="tab = 'settings'">设置</button>
      </div>
      <div class="adm-editor__grid" :data-tab="tab">
        <section class="adm-editor__main" aria-label="正文">
          <Field v-slot="{ id, invalid }" label="标题" :error="errors.title"><input :id="id" v-model="form.title" class="input adm-editor__title" :aria-invalid="invalid" placeholder="页面标题" maxlength="200"></Field>
          <Field v-slot="{ id }" label="别名（网址）" :error="errors.slug" :hint="pageId ? '改了别名，旧地址会自动跳到新地址。' : '页面地址就是 /别名，比如 /about。'"><div class="adm-slug"><span>/</span><input :id="id" v-model="form.slug" class="input" spellcheck="false" @input="slugTouched = true"></div></Field>
          <div class="adm-editor__panes">
            <div class="adm-editor__pane adm-editor__pane--write"><MarkdownEditor ref="editor" v-model="form.content_md" :upload="upload" placeholder="用 Markdown 写页面内容。" @pick-image="pickerOpen = true" @save="save()" @scroll="(r) => preview?.setScroll(r)" /></div>
            <div class="adm-editor__pane adm-editor__pane--preview"><PreviewPane ref="preview" :markdown="form.content_md" /></div>
          </div>
        </section>
        <aside class="adm-editor__side adm-editor__side--inline" aria-label="页面设置">
          <section class="adm-card adm-panel">
            <h2>发布</h2>
            <Segmented v-model="form.status" label="状态" :options="statusOptions" />
            <Field v-slot="{ id }" label="发布时间" hint="留空 = 保存时的现在。"><input :id="id" v-model="form.published_at" class="input" type="datetime-local"></Field>
            <button v-if="pageId" class="btn btn--sm btn--danger" type="button" @click="trash"><AIcon name="a-trash" />移入回收站</button>
          </section>
          <section class="adm-card adm-panel">
            <h2>版式与位置</h2>
            <Field label="模板"><Segmented v-model="form.template" label="页面模板" :options="templateOptions" /></Field>
            <SwitchField v-model="form.in_nav" label="放进顶栏导航" hint="会在“导航与页脚”里自动加一项" />
            <SwitchField v-model="form.in_footer" label="放进页脚导航" />
          </section>
          <section class="adm-card adm-panel">
            <h2>搜索引擎与分享</h2>
            <Field v-slot="{ id }" label="标题" hint="留空用页面标题"><input :id="id" v-model="form.seo_title" class="input" maxlength="200"></Field>
            <Field v-slot="{ id }" label="描述"><textarea :id="id" v-model="form.seo_description" class="textarea" rows="2" maxlength="400" /></Field>
            <Field label="分享图"><CoverPicker :media="form.seo_image" title="选择分享图" @pick="(m) => (form.seo_image = m)" /></Field>
          </section>
        </aside>
      </div>
      <MediaPicker :open="pickerOpen" multiple title="选择图片" @close="pickerOpen = false" @pick="onPick" />
      <RevisionDrawer v-if="pageId" :open="historyOpen" :base="`/pages/${pageId}`" :current-markdown="form.content_md" :current-title="form.title" @close="historyOpen = false" @restore="restoreRevision" />
    </template>
  </div>
</template>
