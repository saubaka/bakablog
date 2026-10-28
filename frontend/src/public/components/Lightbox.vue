<script setup lang="ts">
/* Full-screen picture viewer: arrows, swipe, keyboard, caption and count. Opened with openLightbox(); one instance lives in App.
   The viewer fades in and out, and a picture is replaced by the next one from the side the visitor is going to (the old one leaves, the new one comes in). */
import { computed, nextTick, ref, shallowRef, watch } from 'vue'
import Icon from '@/ui/components/Icon'
import { closeLightbox, lightbox } from '../lightbox'

const root = ref<HTMLElement | null>(null)
const closeBtn = ref<HTMLButtonElement | null>(null)
const index = ref(0)
const dir = ref<'next' | 'prev'>('next')
const open = computed(() => !!lightbox.value)
/** What the viewer shows while it fades out: the pictures stay until it is gone (the store is emptied the moment it closes). */
const last = shallowRef(lightbox.value)
watch(lightbox, (v) => { if (v) last.value = v })
const items = computed(() => (lightbox.value ?? last.value)?.items ?? [])
const item = computed(() => items.value[index.value])
const many = computed(() => items.value.length > 1)
let x0: number | null = null

function show(k: number): void {
  const n = items.value.length
  if (n) index.value = ((k % n) + n) % n
}
function step(d: 1 | -1): void {
  dir.value = d === 1 ? 'next' : 'prev'
  show(index.value + d)
}

function onKey(e: KeyboardEvent): void {
  if (!open.value) return
  if (e.key === 'Escape') { e.preventDefault(); closeLightbox() }
  else if (e.key === 'ArrowLeft') step(-1)
  else if (e.key === 'ArrowRight') step(1)
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
  if (Math.abs(dx) > 50 && many.value) step(dx < 0 ? 1 : -1)
}

watch(lightbox, async (v) => {
  if (v) {
    index.value = v.index
    dir.value = 'next'
    document.addEventListener('keydown', onKey)
    await nextTick()
    closeBtn.value?.focus({ preventScroll: true })
  } else {
    document.removeEventListener('keydown', onKey)
  }
})
</script>

<template>
  <Transition name="lb">
    <div v-if="open" ref="root" class="lightbox" :data-dir="dir" role="dialog" aria-modal="true" aria-label="图片查看" @click.self="closeLightbox" @pointerdown="onDown" @pointerup="onUp">
      <div class="lightbox__bar">
        <Transition name="tick" mode="out-in"><span :key="index">{{ index + 1 }} / {{ items.length }}</span></Transition>
        <button ref="closeBtn" class="icon-btn" type="button" aria-label="关闭" @click="closeLightbox"><Icon name="close" /></button>
      </div>
      <button v-if="many" class="icon-btn lightbox__nav lightbox__nav--prev" type="button" aria-label="上一张" @click="step(-1)"><Icon name="arrow-l" /></button>
      <Transition name="lbimg" mode="out-in">
        <img v-if="item" :key="`${index}|${item.src}`" class="lightbox__img" :src="item.src" :alt="item.alt" draggable="false">
      </Transition>
      <button v-if="many" class="icon-btn lightbox__nav lightbox__nav--next" type="button" aria-label="下一张" @click="step(1)"><Icon name="arrow-r" /></button>
      <Transition name="tick" mode="out-in"><p :key="index" class="lightbox__cap">{{ item?.caption || item?.alt }}</p></Transition>
    </div>
  </Transition>
</template>
