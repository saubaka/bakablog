<script setup lang="ts">
/* A block of content that is replaced as a whole when `k` changes (another page of results, a new search, another month, cards turning into rows):
   the old content leaves, the box glides from its height to the height of the new content, and the new content enters. `dir` says which way the change reads
   ("next" moves the content in from the right, "prev" from the left, "none" is a fade). The scroll motion of the pieces inside (v-fx) plays on top, as for any new content. */
import { ref } from 'vue'
import { FX } from '@/fx/engine'
import { motionOn, type Dir } from '../motion'

defineProps<{ k: string | number; dir?: Dir; paneClass?: string }>()

const box = ref<HTMLElement | null>(null)
let from = 0
let glide: Animation | null = null

const EASE = 'cubic-bezier(.22, .8, .3, 1)'

function release(): void {
  const b = box.value
  if (!b) return
  b.style.removeProperty('height')
  b.style.removeProperty('overflow')
  FX.refresh()          // whatever sits below moved: measure it again
}

/** The old content starts to leave: pin the box at its height, so the page below does not jump when the content disappears. */
function beforeLeave(): void {
  const b = box.value
  if (!b || !motionOn()) return
  glide?.cancel()
  glide = null
  from = b.offsetHeight
  b.style.height = `${from}px`
  b.style.overflow = 'hidden'
}

/** The new content is in: glide from the old height to its height. */
function enter(el: Element): void {
  const b = box.value
  if (!b) return
  const start = from
  from = 0
  if (!motionOn() || !start || typeof b.animate !== 'function') { release(); return }
  const to = (el as HTMLElement).offsetHeight
  if (Math.abs(to - start) < 2) { release(); return }
  b.style.height = `${to}px`
  b.style.overflow = 'hidden'
  glide = b.animate([{ height: `${start}px` }, { height: `${to}px` }], { duration: Math.min(260 + Math.abs(to - start) * 0.35, 520), easing: EASE })
  glide.finished.then(release, () => undefined)
}
</script>

<template>
  <div ref="box" class="swap" :data-dir="dir ?? 'none'">
    <Transition name="swap" mode="out-in" @before-leave="beforeLeave" @enter="enter">
      <div :key="k" class="swap__pane" :class="paneClass"><slot /></div>
    </Transition>
  </div>
</template>
