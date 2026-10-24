<script setup lang="ts">
/* A dialog for forms and pickers. v-model:open; Esc and a click on the backdrop close it; focus goes in, and back to where it was. */
import { nextTick, ref, watch } from 'vue'
import AIcon from './AIcon'

const props = withDefaults(defineProps<{ open: boolean; title: string; wide?: boolean; label?: string }>(), { wide: false, label: '' })
const emit = defineEmits<{ 'update:open': [boolean]; close: [] }>()
const dlg = ref<HTMLDialogElement | null>(null)

watch(() => props.open, async (open) => {
  const d = dlg.value
  if (!d) return
  if (open && !d.open) { d.showModal(); await nextTick(); (d.querySelector<HTMLElement>('[data-autofocus]') ?? d.querySelector<HTMLElement>('input, textarea, select, button:not(.adm-modal__x)'))?.focus() }
  else if (!open && d.open) d.close()
}, { flush: 'post' })

function closed(): void {
  if (dlg.value?.open) return          // a stale event from before the dialog was opened again
  emit('update:open', false)
  emit('close')
}
</script>

<template>
  <dialog ref="dlg" class="dialog adm-modal" :class="{ 'adm-modal--wide': wide }" :aria-label="label || title" @close="closed" @click.self="dlg?.close()">
    <div v-if="open" class="adm-modal__in">
      <header class="adm-modal__head">
        <h2>{{ title }}</h2>
        <button class="icon-btn icon-btn--ghost adm-modal__x" type="button" aria-label="关闭" @click="dlg?.close()"><AIcon name="close" /></button>
      </header>
      <div class="adm-modal__body"><slot /></div>
      <footer v-if="$slots.footer" class="dialog__actions"><slot name="footer" /></footer>
    </div>
  </dialog>
</template>
