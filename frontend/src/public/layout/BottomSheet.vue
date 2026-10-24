<script setup lang="ts">
/* A drawer from the bottom edge: table of contents, "more" menu. Closes with Esc, a tap on the scrim or a link inside it.
   Focus moves into the sheet when it opens and back to the control that opened it when it closes; Tab stays inside. */
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps<{ open: boolean; label: string }>()
const emit = defineEmits<{ close: [] }>()
const el = ref<HTMLElement | null>(null)
let opener: HTMLElement | null = null

function focusables(): HTMLElement[] {
  return [...(el.value?.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])') ?? [])]
}

function onKey(e: KeyboardEvent): void {
  if (e.key === 'Escape') { e.preventDefault(); emit('close'); return }
  if (e.key !== 'Tab') return
  const list = focusables()
  const first = list[0]
  const last = list[list.length - 1]
  if (!first || !last) return
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
}

watch(() => props.open, async (open) => {
  if (open) {
    opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
    document.addEventListener('keydown', onKey)
    await nextTick()
    ;(focusables()[0] ?? el.value)?.focus({ preventScroll: true })
  } else {
    document.removeEventListener('keydown', onKey)
    opener?.focus({ preventScroll: true })
    opener = null
  }
})
onBeforeUnmount(() => document.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="scrim" :class="{ 'is-open': open }" @click="emit('close')" />
  <div ref="el" class="sheet" :class="{ 'is-open': open }" role="dialog" aria-modal="true" :aria-label="label" :aria-hidden="open ? undefined : 'true'" tabindex="-1" @click="(e) => (e.target as HTMLElement).closest('a') && emit('close')">
    <div class="sheet__grab" />
    <slot />
  </div>
</template>
