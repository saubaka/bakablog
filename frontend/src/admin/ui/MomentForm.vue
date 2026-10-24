<script setup lang="ts">
/* The publish box: write, add pictures (up to nine), a mood, a link card, tags, and when it should appear. Used for new moments and for editing. */
import { computed, reactive, ref, watch } from 'vue'
import { api, AdminError } from '../api/client'
import { mediaThumb, uploadMedia } from '../api/media'
import { fromLocalInput, toLocalInput } from '../format'
import { taxo } from '../taxonomy'
import type { AdminMoment, AdminMedia, LinkPreview, Visibility } from '../types'
import AIcon from './AIcon'
import MediaPicker from './MediaPicker.vue'
import MoodPicker from './MoodPicker.vue'
import Segmented from './Segmented.vue'
import SwitchField from './SwitchField.vue'
import TagInput from './TagInput.vue'
import { useSortable } from './sortable'
import { toast, toastError } from './toast'

const props = withDefaults(defineProps<{ moment?: AdminMoment | null; compact?: boolean }>(), { moment: null, compact: false })
const emit = defineEmits<{ saved: [m: AdminMoment]; cancel: [] }>()
const MAX = 9

interface Pic { id: number; alt: string; src: string; color: string; busy?: boolean }
const text = ref('')
const pics = ref<Pic[]>([])
const mood = ref<string | null>(null)
const tags = ref<string[]>([])
const visibility = ref<Visibility>('public')
const pinned = ref(false)
const when = ref('')
const card = reactive({ url: '', title: '', description: '', icon_media_id: null as number | null, domain: '', open: false, loading: false })
const picker = ref(false)
const saving = ref(false)
const area = ref<HTMLTextAreaElement | null>(null)
const drop = ref(false)
const sort = useSortable(() => pics.value, (n) => { pics.value = n })

function reset(m: AdminMoment | null): void {
  text.value = m?.markdown ?? ''
  pics.value = (m?.media ?? []).map((x) => ({ id: x.id, alt: x.alt_override ?? x.alt ?? '', src: mediaThumb(x as never, 480), color: x.color }))
  mood.value = m?.mood?.id ?? null
  tags.value = m?.tags.map((t) => t.name) ?? []
  visibility.value = m?.visibility ?? 'public'
  pinned.value = m?.pinned ?? false
  when.value = m ? toLocalInput(m.published_at) : ''
  const c = m?.link_card
  Object.assign(card, { url: c?.url ?? '', title: c?.title ?? '', description: c?.description ?? '', icon_media_id: null, domain: c?.domain ?? '', open: !!c, loading: false })
}
watch(() => props.moment, (m) => reset(m ?? null), { immediate: true })
defineExpose({ focus: () => area.value?.focus(), reset: () => reset(props.moment ?? null) })

const full = computed(() => pics.value.length >= MAX)
const empty = computed(() => !text.value.trim() && !pics.value.length && !card.url.trim())

async function addFiles(files: File[]): Promise<void> {
  const pictures = files.filter((f) => f.type.startsWith('image/')).slice(0, MAX - pics.value.length)
  for (const f of pictures) {
    const tmp: Pic = { id: -Date.now() - Math.random(), alt: '', src: URL.createObjectURL(f), color: '#e6f1fc', busy: true }
    pics.value = [...pics.value, tmp]
    try {
      const m = await uploadMedia(f)
      pics.value = pics.value.map((p) => (p === tmp ? { id: m.id, alt: m.alt, src: mediaThumb(m, 480), color: m.color } : p))
    } catch (e) {
      pics.value = pics.value.filter((p) => p !== tmp)
      toastError(`${f.name}：${e instanceof AdminError ? e.message : '上传失败'}`)
    } finally {
      URL.revokeObjectURL(tmp.src)
    }
  }
}
function onPick(items: AdminMedia[]): void {
  const add = items.filter((m) => !pics.value.some((p) => p.id === m.id)).slice(0, MAX - pics.value.length)
  pics.value = [...pics.value, ...add.map((m) => ({ id: m.id, alt: m.alt, src: mediaThumb(m, 480), color: m.color }))]
}
function onPaste(e: ClipboardEvent): void { const files = [...(e.clipboardData?.files ?? [])]; if (files.length) { e.preventDefault(); void addFiles(files) } }
function onDrop(e: DragEvent): void { drop.value = false; const files = [...(e.dataTransfer?.files ?? [])]; if (files.length) { e.preventDefault(); void addFiles(files) } }

async function fetchCard(): Promise<void> {
  const url = card.url.trim()
  if (!/^https?:\/\//i.test(url)) { toastError('链接要以 http:// 或 https:// 开头。'); return }
  card.loading = true
  try {
    const r = await api.post<LinkPreview>('/moments/link-preview', { url })
    Object.assign(card, { url: r.url, title: r.title, description: r.description, domain: r.domain, icon_media_id: r.icon_media_id })
  } catch (e) { toastError(e instanceof AdminError ? e.message : '抓取失败，可以手动填标题。') } finally { card.loading = false }
}

async function submit(): Promise<void> {
  if (empty.value) { toastError('写点什么，或者加一张图片。'); return }
  if (pics.value.some((p) => p.busy)) { toastError('图片还在上传，稍等一下。'); return }
  saving.value = true
  try {
    const body = {
      text: text.value, mood: mood.value, tags: tags.value, media: pics.value.map((p) => ({ media_id: p.id, alt: p.alt })),
      link_card: card.url.trim() ? { url: card.url.trim(), title: card.title, description: card.description, icon_media_id: card.icon_media_id } : null,
      pinned: pinned.value, visibility: visibility.value, published_at: fromLocalInput(when.value),
    }
    const saved = props.moment ? await api.patch<AdminMoment>(`/moments/${props.moment.id}`, body) : await api.post<AdminMoment>('/moments', body)
    toast(props.moment ? '动态已更新。' : saved.scheduled ? '动态已设为定时发布。' : '动态已发布。')
    if (!props.moment) reset(null)
    emit('saved', saved)
  } catch (e) {
    toastError(e instanceof AdminError ? (e.firstField ? `${e.message}（${e.firstField}）` : e.message) : '没有成功，请再试一次。')
  } finally { saving.value = false }
}
const visOptions = [{ value: 'public', label: '公开' }, { value: 'unlisted', label: '仅链接可见' }, { value: 'private', label: '私密' }]
</script>

<template>
  <form class="adm-mform" :class="{ 'is-drop': drop }" @submit.prevent="submit" @dragover.prevent="drop = true" @dragleave="drop = false" @drop="onDrop">
    <label class="sr-only" for="adm-moment-text">动态内容</label>
    <textarea id="adm-moment-text" ref="area" v-model="text" class="textarea adm-mform__text" :rows="compact ? 3 : 4" placeholder="此刻想说点什么？可以用 **粗体**、链接；#标签 会自动识别。可以粘贴或拖进图片。" @paste="onPaste" />
    <ul v-if="pics.length" class="adm-mform__pics" aria-label="已添加的图片">
      <li v-for="(p, i) in pics" :key="p.id" class="adm-mpic" :class="{ 'is-dragging': sort.dragging.value === i }" data-sort-row>
        <div class="adm-mpic__img"><img :src="p.src" :alt="''" :style="{ backgroundColor: p.color }"><span v-if="p.busy" class="adm-mpic__busy">上传中</span></div>
        <input v-model="p.alt" class="input adm-mpic__alt" :aria-label="`第 ${i + 1} 张图片的替代文字`" placeholder="替代文字" :disabled="p.busy">
        <div class="adm-mpic__tools">
          <button type="button" class="adm-grip" :aria-label="`拖动调整第 ${i + 1} 张的位置`" v-bind="sort.handle(i)"><AIcon name="a-grip" /></button>
          <button type="button" class="icon-btn icon-btn--ghost" :aria-label="`移除第 ${i + 1} 张`" @click="pics = pics.filter((x) => x !== p)"><AIcon name="close" /></button>
        </div>
      </li>
    </ul>
    <p class="sr-only" role="status" aria-live="polite">{{ sort.announce.value }}</p>

    <div v-if="card.open" class="adm-mform__card">
      <div class="adm-mform__cardrow">
        <input v-model="card.url" class="input" type="url" placeholder="https://……" aria-label="链接地址" @keydown.enter.prevent="fetchCard">
        <button class="btn btn--sm" type="button" :disabled="card.loading || !card.url" @click="fetchCard">{{ card.loading ? '正在抓取……' : '抓取标题' }}</button>
        <button class="icon-btn icon-btn--ghost" type="button" aria-label="去掉链接卡片" @click="Object.assign(card, { open: false, url: '', title: '', description: '', icon_media_id: null })"><AIcon name="close" /></button>
      </div>
      <input v-model="card.title" class="input" aria-label="链接标题" placeholder="标题（可以手改）" maxlength="200">
      <input v-model="card.description" class="input" aria-label="链接描述" placeholder="描述（可选）" maxlength="300">
    </div>

    <MoodPicker v-model="mood" />

    <div class="adm-mform__bar">
      <button class="btn btn--sm btn--ghost" type="button" :disabled="full" @click="picker = true"><AIcon name="a-image" />图片库</button>
      <button class="btn btn--sm btn--ghost" type="button" :disabled="full" @click="($refs.file as HTMLInputElement).click()"><AIcon name="a-upload" />上传</button>
      <input ref="file" class="sr-only" type="file" aria-label="选择要添加的图片" accept="image/jpeg,image/png,image/gif,image/webp" multiple tabindex="-1" @change="(e) => { addFiles([...((e.target as HTMLInputElement).files ?? [])]); (e.target as HTMLInputElement).value = '' }">
      <button class="btn btn--sm btn--ghost" type="button" @click="card.open = !card.open"><AIcon name="a-link" />链接卡片</button>
      <span class="adm-hint">{{ pics.length }}/{{ MAX }} 张</span>
    </div>

    <div class="adm-mform__more">
      <div class="field"><span class="label">标签</span><TagInput v-model="tags" :suggestions="taxo.tags.map((t) => t.name)" placeholder="也可以直接在正文里写 #标签" /></div>
      <div class="field"><span class="label">可见性</span><Segmented v-model="visibility" label="可见性" :options="visOptions" /></div>
      <div class="field"><label class="label" for="adm-moment-when">发布时间</label><input id="adm-moment-when" v-model="when" class="input" type="datetime-local"><small>留空 = 现在；补发过去的、定时将来的都可以。</small></div>
      <SwitchField v-model="pinned" label="置顶" hint="显示在动态页最上面" />
    </div>

    <div class="adm-mform__actions">
      <button v-if="moment" class="btn btn--ghost" type="button" @click="emit('cancel')">取消</button>
      <button class="btn btn--fill" type="submit" :disabled="saving || empty"><template v-if="saving">正在保存……</template><template v-else>{{ moment ? '保存修改' : '发布' }}</template></button>
    </div>
    <MediaPicker :open="picker" multiple title="从图片库选择" @close="picker = false" @pick="onPick" />
  </form>
</template>
