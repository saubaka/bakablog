<script setup lang="ts">
/* A side panel for details (a picture, a revision, a log entry): slides in from the right; on a phone it is a sheet from the bottom. */
import { nextTick, ref, watch } from 'vue'
import AIcon from './AIcon'

const props = defineProps<{ open: boolean; title: string }>()
const emit = defineEmits<{ close: [] }>()
const el = ref<HTMLElement | null>(null)
let opener: HTMLElement | null = null

function focusables(): HTMLElement[] {
  return [...(el.value?.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])') ?? [])]
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
    ;(el.value?.querySelector<HTMLElement>('[data-autofocus]') ?? focusables()[1] ?? el.value)?.focus({ preventScroll: true })
  } else {
    document.removeEventListener('keydown', onKey)
    opener?.focus({ preventScroll: true })
  }
})
</script>

<template>
  <div class="scrim adm-scrim" :class="{ 'is-open': open }" @click="emit('close')" />
  <aside ref="el" class="adm-drawer" :class="{ 'is-open': open }" role="dialog" aria-modal="true" :aria-label="title" :aria-hidden="open ? undefined : 'true'" tabindex="-1" :inert="open ? undefined : true">
    <header class="adm-drawer__head">
      <h2>{{ title }}</h2>
      <button class="icon-btn icon-btn--ghost" type="button" aria-label="关闭" @click="emit('close')"><AIcon name="close" /></button>
    </header>
    <div class="adm-drawer__body"><slot v-if="open" /></div>
    <footer v-if="$slots.footer && open" class="adm-drawer__foot"><slot name="footer" /></footer>
  </aside>
</template>
