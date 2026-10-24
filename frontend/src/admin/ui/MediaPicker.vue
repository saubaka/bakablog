<script setup lang="ts">
/* Choose pictures from the library (or add new ones on the spot). Used by the editor, covers, avatars, the home polaroid ... */
import { ref, watch } from 'vue'
import { api, AdminError } from '../api/client'
import { mediaThumb, uploadMedia } from '../api/media'
import type { AdminMedia, ListPage } from '../types'
import { debounced } from '../use'
import AIcon from './AIcon'
import Modal from './Modal.vue'
import Pagination from './Pagination.vue'
import { toastError } from './toast'

const props = withDefaults(defineProps<{ open: boolean; multiple?: boolean; title?: string; kind?: 'image' | 'icon' }>(), { multiple: false, title: '选择图片', kind: 'image' })
const emit = defineEmits<{ close: []; pick: [items: AdminMedia[]] }>()
const items = ref<AdminMedia[]>([])
const page = ref(1)
const pages = ref(1)
const q = ref('')
const loading = ref(false)
const chosen = ref<AdminMedia[]>([])
const uploading = ref(0)
const file = ref<HTMLInputElement | null>(null)

async function load(): Promise<void> {
  loading.value = true
  try {
    const r = await api.get<ListPage<AdminMedia>>('/media', { q: q.value.trim(), page: page.value, per: 24, kind: props.kind })
    items.value = r.items
    pages.value = r.pages
  } catch (e) { toastError(e instanceof AdminError ? e.message : '图片列表加载失败。') } finally { loading.value = false }
}
const search = debounced(() => { page.value = 1; void load() }, 300)
watch(() => props.open, (o) => { if (o) { chosen.value = []; q.value = ''; page.value = 1; void load() } })

function toggle(m: AdminMedia): void {
  if (!props.multiple) { emit('pick', [m]); emit('close'); return }
  chosen.value = chosen.value.some((c) => c.id === m.id) ? chosen.value.filter((c) => c.id !== m.id) : [...chosen.value, m]
}
const isChosen = (m: AdminMedia): boolean => chosen.value.some((c) => c.id === m.id)

async function upload(list: File[]): Promise<void> {
  const pics = list.filter((f) => f.type.startsWith('image/'))
  uploading.value += pics.length
  const added: AdminMedia[] = []
  for (const f of pics) {
    try { added.push(await uploadMedia(f)) } catch (e) { toastError(`${f.name}：${e instanceof AdminError ? e.message : '上传失败'}`) } finally { uploading.value -= 1 }
  }
  if (!added.length) return
  if (!props.multiple) { emit('pick', [added[0] as AdminMedia]); emit('close'); return }
  chosen.value = [...chosen.value, ...added.filter((a) => !isChosen(a))]
  page.value = 1
  await load()
}
function onFiles(e: Event): void { const input = e.target as HTMLInputElement; void upload([...(input.files ?? [])]); input.value = '' }
function onDrop(e: DragEvent): void { e.preventDefault(); void upload([...(e.dataTransfer?.files ?? [])]) }
</script>

<template>
  <Modal :open="open" :title="title" wide @close="emit('close')">
    <div class="adm-picker" @dragover.prevent @drop="onDrop">
      <div class="adm-toolbar">
        <div class="searchfield"><AIcon name="search" /><input v-model="q" class="input" type="search" placeholder="按文件名、替代文字搜索" aria-label="搜索图片" data-autofocus @input="search()"></div>
        <button class="btn btn--sm" type="button" @click="file?.click()"><AIcon name="a-upload" />上传新图片</button>
        <input ref="file" class="sr-only" type="file" aria-label="选择要上传的图片" accept="image/jpeg,image/png,image/gif,image/webp" multiple tabindex="-1" @change="onFiles">
        <span v-if="uploading" role="status" class="adm-picker__busy">正在上传 {{ uploading }} 张……</span>
      </div>
      <ul v-if="items.length" class="adm-media-grid adm-media-grid--pick">
        <li v-for="m in items" :key="m.id">
          <button type="button" class="adm-media-tile" :class="{ 'is-on': isChosen(m) }" :aria-pressed="multiple ? isChosen(m) : undefined" :title="m.filename" @click="toggle(m)">
            <img :src="mediaThumb(m)" :alt="m.alt || m.filename" :style="{ backgroundColor: m.color }" loading="lazy">
            <span v-if="multiple" class="adm-media-tile__check"><AIcon name="check" /></span>
            <small>{{ m.alt || m.filename }}</small>
          </button>
        </li>
      </ul>
      <p v-else-if="!loading" class="adm-picker__empty">图片库里还没有图片。点“上传新图片”，或者把文件拖到这里。</p>
      <Pagination :page="page" :pages="pages" @go="(n) => { page = n; load() }" />
    </div>
    <template v-if="multiple" #footer>
      <span class="adm-picker__n">已选 {{ chosen.length }} 张</span>
      <button class="btn btn--ghost" type="button" @click="emit('close')">取消</button>
      <button class="btn btn--fill" type="button" :disabled="!chosen.length" @click="emit('pick', chosen); emit('close')">插入</button>
    </template>
  </Modal>
</template>
