<script setup lang="ts">
/* A picture chosen by id (logo, favicon, avatar, share image ...): shows what is chosen, lets the person pick another or clear it. */
import { ref, watch } from 'vue'
import { api } from '../api/client'
import { mediaThumb } from '../api/media'
import type { AdminMedia } from '../types'
import AIcon from './AIcon'
import MediaPicker from './MediaPicker.vue'

const props = defineProps<{ title: string; kind?: 'image' | 'icon' }>()
const model = defineModel<number | null>({ required: true })
const media = ref<AdminMedia | null>(null)
const open = ref(false)

watch(() => model.value, async (id) => {
  if (!id) { media.value = null; return }
  if (media.value?.id === id) return
  try { media.value = await api.get<AdminMedia>(`/media/${id}`) } catch { media.value = null }
}, { immediate: true })
void props
</script>

<template>
  <div class="adm-mediafield">
    <span class="adm-mediafield__pic"><img v-if="media" :src="mediaThumb(media)" :alt="media.alt || media.filename" :style="{ backgroundColor: media.color }"><AIcon v-else name="a-image" /></span>
    <span class="adm-mediafield__text"><b>{{ media ? media.filename : '还没有选择' }}</b><small v-if="media">{{ media.orig_width }}×{{ media.orig_height }}</small></span>
    <button class="btn btn--sm" type="button" @click="open = true">{{ media ? '更换' : '选择' }}</button>
    <button v-if="media" class="btn btn--sm btn--ghost" type="button" @click="model = null">移除</button>
    <MediaPicker :open="open" :title="title" :kind="kind" @close="open = false" @pick="(items) => { model = items[0]?.id ?? null; media = items[0] ?? null }" />
  </div>
</template>
