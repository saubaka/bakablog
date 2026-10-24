<script setup lang="ts">
/* A small popover menu: a button that opens a list of actions. Esc and an outside click close it; arrow keys move; focus returns to the button. */
import { nextTick, onBeforeUnmount, ref, useId } from 'vue'
import AIcon from './AIcon'

withDefaults(defineProps<{ label: string; icon?: string; primary?: boolean; align?: 'start' | 'end'; iconOnly?: boolean }>(), { icon: '', primary: false, align: 'end', iconOnly: false })
const open = ref(false)
const root = ref<HTMLElement | null>(null)
const button = ref<HTMLButtonElement | null>(null)
const id = useId()

function items(): HTMLElement[] { return [...(root.value?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [])] }
function onDocClick(e: MouseEvent): void { if (!root.value?.contains(e.target as Node)) close() }
function close(refocus = false): void {
  open.value = false
  document.removeEventListener('click', onDocClick, true)
  if (refocus) button.value?.focus()
}
async function toggle(): Promise<void> {
  if (open.value) { close(); return }
  open.value = true
  document.addEventListener('click', onDocClick, true)
  await nextTick()
  items()[0]?.focus()
}
function onKey(e: KeyboardEvent): void {
  if (!open.value) { if (e.key === 'ArrowDown') { e.preventDefault(); void toggle() } return }
  const list = items()
  const i = list.indexOf(document.activeElement as HTMLElement)
  if (e.key === 'Escape') { e.preventDefault(); close(true) }
  else if (e.key === 'ArrowDown') { e.preventDefault(); list[(i + 1) % list.length]?.focus() }
  else if (e.key === 'ArrowUp') { e.preventDefault(); list[(i - 1 + list.length) % list.length]?.focus() }
  else if (e.key === 'Tab') close()
}
onBeforeUnmount(() => document.removeEventListener('click', onDocClick, true))
defineExpose({ close })
</script>

<template>
  <div ref="root" class="adm-menu" @keydown="onKey">
    <button ref="button" class="btn" :class="[primary ? 'btn--fill' : 'btn--ghost', { 'btn--icon': iconOnly }]" type="button" aria-haspopup="menu" :aria-expanded="open" :aria-controls="id" :aria-label="iconOnly ? label : undefined" @click="toggle">
      <AIcon v-if="icon" :name="icon" /><span v-if="!iconOnly">{{ label }}</span><AIcon v-if="!iconOnly" name="a-chevron-d" class="adm-menu__caret" />
    </button>
    <div v-show="open" :id="id" class="adm-menu__list" :class="`is-${align}`" role="menu" @click="close()">
      <slot />
    </div>
  </div>
</template>
