<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { copyText } from '@/shared/clipboard'
import { api, AdminError } from '../api/client'
import { mediaThumb, uploadMedia } from '../api/media'
import { bytes, when } from '../format'
import type { AdminMedia, ListPage, MediaUsage } from '../types'
import AIcon from '../ui/AIcon'
import { confirm } from '../ui/confirm'
import Drawer from '../ui/Drawer.vue'
import EmptyBox from '../ui/EmptyBox.vue'
import PageHead from '../ui/PageHead.vue'
import Pagination from '../ui/Pagination.vue'
import { toast, toastError } from '../ui/toast'
import { debounced, useLoader, useRouteQuery } from '../use'

interface Upload { key: number; name: string; progress: number; error: string; file: File }
const route = useRoute()
const { state, set } = useRouteQuery({ q: '', kind: '', unused: '', alt: '', trashed: '', sort: 'new', page: '1' })
const search = ref(state.value.q)
const { data, loading, error, reload } = useLoader((signal) => api.get<ListPage<AdminMedia>>('/media', {
  q: state.value.q, kind: state.value.kind, unused: state.value.unused === '1', alt: state.value.alt, trashed: state.value.trashed === '1', sort: state.value.sort, page: state.value.page, per: 36,
}, signal), () => state.value)
const applySearch = debounced((v: string) => set({ q: v.trim() }), 350)
watch(() => state.value.q, (v) => { search.value = v })
const trashView = computed(() => state.value.trashed === '1')

/* ---- upload queue ---- */
const queue = ref<Upload[]>([])
const fileInput = ref<HTMLInputElement | null>(null)
const dropzone = ref<HTMLElement | null>(null)
const hot = ref(false)
let next = 1
async function send(u: Upload): Promise<void> {
  u.error = ''
  u.progress = 0
  try { await uploadMedia(u.file, { onProgress: (f) => { u.progress = f } }); queue.value = queue.value.filter((x) => x !== u); await reload() } catch (e) { u.error = e instanceof AdminError ? e.message : '上传失败' }
}
function addFiles(files: File[]): void {
  const pics = files.filter((f) => f.type.startsWith('image/'))
  if (files.length !== pics.length) toastError('只能上传图片（JPEG、PNG、GIF、WebP）。')
  for (const f of pics) { const u = reactive<Upload>({ key: next++, name: f.name, progress: 0, error: '', file: f }); queue.value.push(u); void send(u) }
}
function onFiles(e: Event): void { const i = e.target as HTMLInputElement; addFiles([...(i.files ?? [])]); i.value = '' }
function onDrop(e: DragEvent): void { e.preventDefault(); hot.value = false; addFiles([...(e.dataTransfer?.files ?? [])]) }
onMounted(() => { if (route.query.upload) dropzone.value?.scrollIntoView({ block: 'center' }) })

/* ---- details ---- */
const shown = ref<(AdminMedia & { usage: MediaUsage[] }) | null>(null)
const form = ref({ alt: '', caption: '', filename: '' })
const saving = ref(false)
const replaceInput = ref<HTMLInputElement | null>(null)
async function open(m: AdminMedia): Promise<void> {
  try {
    const d = await api.get<AdminMedia & { usage: MediaUsage[] }>(`/media/${m.id}`)
    shown.value = d
    form.value = { alt: d.alt, caption: d.caption, filename: d.filename }
  } catch (e) { toastError(e instanceof AdminError ? e.message : '图片详情加载失败。') }
}
async function saveInfo(): Promise<void> {
  if (!shown.value) return
  saving.value = true
  try { const m = await api.patch<AdminMedia>(`/media/${shown.value.id}`, form.value); shown.value = { ...shown.value, ...m }; toast('图片信息已保存（用到它的内容已更新）。'); await reload() } catch (e) { toastError(e instanceof AdminError ? e.message : '保存没有成功。') } finally { saving.value = false }
}
async function replaceFile(e: Event): Promise<void> {
  const input = e.target as HTMLInputElement
  const f = input.files?.[0]
  input.value = ''
  if (!f || !shown.value) return
  const form2 = new FormData()
  form2.append('file', f)
  try { const m = await api.upload<AdminMedia>(`/media/${shown.value.id}/replace`, form2); shown.value = { ...shown.value, ...m }; toast('文件已替换，所有用到它的地方都会显示新图。'); await reload() } catch (err) { toastError(err instanceof AdminError ? err.message : '替换没有成功。') }
}
async function copy(text: string, what: string): Promise<void> { toast((await copyText(text)) ? `${what}已复制。` : '复制失败，请手动复制。') }
async function trash(m: AdminMedia, force = false): Promise<void> {
  try { await api.del(`/media/${m.id}`, force ? { force: 1 } : undefined); toast('已移入回收站。'); shown.value = null; await reload() } catch (e) {
    if (e instanceof AdminError && e.code === 'in_use') {
      const places = (e.extra.usage as MediaUsage[] | undefined)?.map((u) => u.title).slice(0, 5).join('、') ?? ''
      if (await confirm({ title: '这张图片还在使用', text: `${e.message}${places ? `（${places}${(e.extra.usage as unknown[]).length > 5 ? ' 等' : ''}）` : ''}。移入回收站后，这些地方在永久删除前仍会显示它。`, confirm: '仍然删除', danger: true })) await trash(m, true)
    } else toastError(e instanceof AdminError ? e.message : '删除没有成功。')
  }
}
async function restore(m: AdminMedia): Promise<void> { try { await api.post(`/media/${m.id}/restore`); toast('已恢复。'); shown.value = null; await reload() } catch (e) { toastError(e instanceof AdminError ? e.message : '恢复没有成功。') } }
async function purge(m: AdminMedia): Promise<void> {
  if (!(await confirm({ title: '永久删除这张图片？', text: m.usage_count ? `用到它的 ${m.usage_count} 处会显示“图片缺失”的占位。文件会被彻底删除。` : '文件会被彻底删除，不能再恢复。', confirm: '永久删除', danger: true }))) return
  try { await api.del(`/media/${m.id}/purge`); toast('已永久删除。'); shown.value = null; await reload() } catch (e) { toastError(e instanceof AdminError ? e.message : '删除没有成功。') }
}
const adminLink = (u: MediaUsage): string => (u.admin_url ?? '').replace(/^\/admin/, '') || '/'
const typeLabel: Record<string, string> = { post: '文章', moment: '动态', page: '页面', home_block: '首页', settings: '设置', series: '系列' }
</script>

<template>
  <div>
    <PageHead title="媒体库" sub="所有上传过的图片。服务器会去掉定位等元数据，并生成三档 WebP。">
      <button class="btn btn--fill" type="button" @click="fileInput?.click()"><AIcon name="a-upload" />上传图片</button>
    </PageHead>
    <input ref="fileInput" class="sr-only" type="file" aria-label="选择要上传的图片" accept="image/jpeg,image/png,image/gif,image/webp" multiple tabindex="-1" @change="onFiles">

    <div v-if="!trashView" ref="dropzone" class="filedrop adm-drop" :class="{ 'is-hot': hot }" @dragover.prevent="hot = true" @dragleave="hot = false" @drop="onDrop">
      <AIcon name="a-upload" /><span><strong>把图片拖到这里</strong>，或点击上面的按钮。可以一次选很多张。</span>
    </div>
    <ul v-if="queue.length" class="adm-queue" aria-label="上传队列">
      <li v-for="u in queue" :key="u.key"><span class="adm-queue__name">{{ u.name }}</span>
        <span v-if="u.error" class="adm-queue__err" role="alert">{{ u.error }} <button class="text-link" type="button" @click="send(u)">重试</button> · <button class="text-link" type="button" @click="queue = queue.filter((x) => x !== u)">放弃</button></span>
        <progress v-else :value="u.progress" max="1" :aria-label="`${u.name} 上传进度`" /></li>
    </ul>

    <div class="adm-toolbar">
      <div class="searchfield"><AIcon name="search" /><input v-model="search" class="input" type="search" placeholder="按文件名、替代文字、说明搜索" aria-label="搜索图片" @input="applySearch(search)"></div>
      <select class="select" aria-label="类型" :value="state.kind" @change="set({ kind: ($event.target as HTMLSelectElement).value })"><option value="">图片</option><option value="icon">站点图标</option></select>
      <select class="select" aria-label="排序" :value="state.sort" @change="set({ sort: ($event.target as HTMLSelectElement).value })"><option value="new">最新上传</option><option value="old">最早上传</option><option value="name">文件名</option><option value="size">体积</option></select>
      <button class="tag" type="button" :aria-pressed="state.unused === '1'" @click="set({ unused: state.unused === '1' ? '' : '1' })">没被使用</button>
      <button class="tag" type="button" :aria-pressed="state.alt === 'missing'" @click="set({ alt: state.alt === 'missing' ? '' : 'missing' })">缺替代文字</button>
      <button class="tag" type="button" :aria-pressed="trashView" @click="set({ trashed: trashView ? '' : '1' })">回收站</button>
    </div>

    <p v-if="error" class="adm-error" role="alert">{{ error.message }} <button class="text-link" type="button" @click="reload">重试</button></p>
    <div v-else-if="loading && !data" class="adm-skel-grid" aria-busy="true"><span v-for="n in 6" :key="n" class="skel adm-skel" /></div>
    <template v-if="data">
      <EmptyBox v-if="!data.items.length" :title="state.q || state.unused || state.alt || trashView ? '没有符合条件的图片' : '图片库是空的'" :text="trashView ? '' : '上传第一张图片吧。'" />
      <ul v-else class="adm-media-grid">
        <li v-for="m in data.items" :key="m.id">
          <button type="button" class="adm-media-tile" :title="m.filename" @click="open(m)">
            <img :src="mediaThumb(m)" :alt="m.alt || m.filename" :style="{ backgroundColor: m.color }" loading="lazy">
            <small>{{ m.alt || m.filename }}</small>
            <span class="adm-media-tile__meta">{{ m.orig_width }}×{{ m.orig_height }} · {{ bytes(m.bytes) }}<template v-if="!m.usage_count && !trashView"> · 未使用</template></span>
          </button>
        </li>
      </ul>
      <Pagination :page="data.page" :pages="data.pages" @go="(n) => set({ page: String(n) }, { keepPage: true })" />
      <p class="adm-count">共 {{ data.total }} 张</p>
    </template>

    <Drawer :open="shown !== null" :title="shown?.filename ?? '图片'" @close="shown = null">
      <template v-if="shown">
        <div class="adm-detail__pic"><img :src="shown.src" :alt="shown.alt || shown.filename" :style="{ backgroundColor: shown.color }"></div>
        <dl class="adm-dl">
          <div><dt>尺寸</dt><dd>{{ shown.orig_width }} × {{ shown.orig_height }}（原图）</dd></div>
          <div><dt>大小</dt><dd>{{ bytes(shown.bytes) }} · {{ shown.mime }}</dd></div>
          <div><dt>上传</dt><dd>{{ when(shown.created_at) }}</dd></div>
        </dl>
        <form class="adm-form" @submit.prevent="saveInfo">
          <label class="field"><span class="label">替代文字</span><input v-model="form.alt" class="input" maxlength="300" placeholder="一句话描述这张图，读屏软件会读它" data-autofocus><small>改了之后，用到这张图的文章、动态会自动更新。</small></label>
          <label class="field"><span class="label">说明（图注）</span><input v-model="form.caption" class="input" maxlength="500"></label>
          <label class="field"><span class="label">文件名</span><input v-model="form.filename" class="input" maxlength="200"></label>
          <button class="btn btn--fill" type="submit" :disabled="saving">保存信息</button>
        </form>
        <div class="adm-detail__copy">
          <button class="btn btn--sm" type="button" @click="copy(shown.src, '图片地址')"><AIcon name="a-copy-link" />复制地址</button>
          <button class="btn btn--sm" type="button" @click="copy(`![${shown.alt}](media:${shown.id})`, 'Markdown 写法')"><AIcon name="a-code" />复制 Markdown</button>
        </div>
        <section>
          <h3 class="adm-h3">使用位置（{{ shown.usage.length }}）</h3>
          <ul v-if="shown.usage.length" class="adm-list adm-list--tight">
            <li v-for="u in shown.usage" :key="`${u.type}${u.id}`"><RouterLink :to="adminLink(u)" @click="shown = null"><span class="adm-badge">{{ typeLabel[u.type] ?? u.type }}</span><span>{{ u.title }}</span><AIcon name="a-chevron-r" class="adm-list__go" /></RouterLink></li>
          </ul>
          <p v-else class="adm-hint">没有任何地方在用它。</p>
        </section>
      </template>
      <template v-if="shown" #footer>
        <template v-if="shown.deleted_at">
          <button class="btn btn--sm" type="button" @click="restore(shown)"><AIcon name="a-undo" />恢复</button>
          <button class="btn btn--sm btn--danger" type="button" @click="purge(shown)"><AIcon name="a-trash" />永久删除</button>
        </template>
        <template v-else>
          <button class="btn btn--sm" type="button" @click="replaceInput?.click()"><AIcon name="a-refresh" />替换文件</button>
          <input ref="replaceInput" class="sr-only" type="file" aria-label="选择替换用的图片" accept="image/jpeg,image/png,image/gif,image/webp" tabindex="-1" @change="replaceFile">
          <button class="btn btn--sm btn--danger" type="button" @click="trash(shown)"><AIcon name="a-trash" />移入回收站</button>
        </template>
      </template>
    </Drawer>
  </div>
</template>
