<script setup lang="ts">
/* A cover picture (or any single picture) with its description and, optionally, a focus point: where the picture is cropped around on cards. */
import { ref } from 'vue'
import type { Media } from '@/shared/types'
import { mediaThumb } from '../api/media'
import type { AdminMedia } from '../types'
import AIcon from '../ui/AIcon'
import MediaPicker from '../ui/MediaPicker.vue'

const props = withDefaults(defineProps<{ media: Media | null; alt?: string; focusX?: number; focusY?: number; withFocus?: boolean; withAlt?: boolean; title?: string }>(), { alt: '', focusX: 50, focusY: 50, withFocus: false, withAlt: false, title: '选择图片' })
const emit = defineEmits<{ pick: [media: AdminMedia | null]; 'update:alt': [string]; 'update:focus': [x: number, y: number] }>()
const open = ref(false)

function onFocus(e: MouseEvent): void {
  const r = (e.currentTarget as HTMLElement).getBoundingClientRect()
  emit('update:focus', Math.round(((e.clientX - r.left) / r.width) * 100), Math.round(((e.clientY - r.top) / r.height) * 100))
}
void props
</script>

<template>
  <div class="adm-cover">
    <div v-if="media" class="adm-cover__pic" :class="{ 'is-pickable': withFocus }" @click="withFocus && onFocus($event)">
      <img :src="mediaThumb(media as never, 960)" :alt="media.alt || ''" :style="{ backgroundColor: media.color }">
      <span v-if="withFocus" class="adm-cover__dot" :style="{ left: `${focusX}%`, top: `${focusY}%` }" aria-hidden="true" />
    </div>
    <p v-if="media && withFocus" class="adm-hint">点一下图片，设置裁切时的视觉中心（卡片是横版时，会围绕它裁）。</p>
    <label v-if="media && withAlt" class="field"><span class="label">替代文字</span><input class="input" :value="alt" placeholder="一句话描述这张图，读屏软件会读它" @input="emit('update:alt', ($event.target as HTMLInputElement).value)"></label>
    <div class="adm-cover__actions">
      <button class="btn btn--sm" type="button" @click="open = true"><AIcon name="a-image" />{{ media ? '更换' : title }}</button>
      <button v-if="media" class="btn btn--sm btn--ghost" type="button" @click="emit('pick', null)">移除</button>
    </div>
    <MediaPicker :open="open" :title="title" @close="open = false" @pick="(items) => emit('pick', items[0] ?? null)" />
  </div>
</template>
