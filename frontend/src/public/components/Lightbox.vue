<script setup lang="ts">
/* Full-screen picture viewer: arrows, swipe, keyboard, caption and count. Opened with openLightbox(); one instance lives in App. */
import { computed, nextTick, ref, watch } from 'vue'
import Icon from '@/ui/components/Icon'
import { closeLightbox, lightbox } from '../lightbox'

const root = ref<HTMLElement | null>(null)
const closeBtn = ref<HTMLButtonElement | null>(null)
const index = ref(0)
const open = computed(() => !!lightbox.value)
const items = computed(() => lightbox.value?.items ?? [])
const item = computed(() => items.value[index.value])
const many = computed(() => items.value.length > 1)
let x0: number | null = null

function show(k: number): void {
  const n = items.value.length
  if (n) index.value = ((k % n) + n) % n
}

function onKey(e: KeyboardEvent): void {
  if (!open.value) return
  if (e.key === 'Escape') { e.preventDefault(); closeLightbox() }
  else if (e.key === 'ArrowLeft') show(index.value - 1)
  else if (e.key === 'ArrowRight') show(index.value + 1)
  else if (e.key === 'Tab') {
    const f = [...(root.value?.querySelectorAll<HTMLElement>('button:not([hidden])') ?? [])]
    const first = f[0]
    const last = f[f.length - 1]
    if (!first || !last) return
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
  }
}

function onDown(e: PointerEvent): void {
  x0 = e.clientX
}

function onUp(e: PointerEvent): void {
  if (x0 === null) return
  const dx = e.clientX - x0
  x0 = null
  if (Math.abs(dx) > 50 && many.value) show(dx < 0 ? index.value + 1 : index.value - 1)
}

watch(lightbox, async (v) => {
  if (v) {
    index.value = v.index
    document.addEventListener('keydown', onKey)
    await nextTick()
    closeBtn.value?.focus({ preventScroll: true })
  } else {
    document.removeEventListener('keydown', onKey)
  }
})
</script>

<template>
  <div v-if="open" ref="root" class="lightbox is-open" role="dialog" aria-modal="true" aria-label="图片查看" @click.self="closeLightbox" @pointerdown="onDown" @pointerup="onUp">
    <div class="lightbox__bar">
      <span>{{ index + 1 }} / {{ items.length }}</span>
      <button ref="closeBtn" class="icon-btn" type="button" aria-label="关闭" @click="closeLightbox"><Icon name="close" /></button>
    </div>
    <button v-if="many" class="icon-btn lightbox__nav lightbox__nav--prev" type="button" aria-label="上一张" @click="show(index - 1)"><Icon name="arrow-l" /></button>
    <img v-if="item" class="lightbox__img" :src="item.src" :alt="item.alt" draggable="false">
    <button v-if="many" class="icon-btn lightbox__nav lightbox__nav--next" type="button" aria-label="下一张" @click="show(index + 1)"><Icon name="arrow-r" /></button>
    <p class="lightbox__cap">{{ item?.caption || item?.alt }}</p>
  </div>
</template>
