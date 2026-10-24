<script setup lang="ts">
/* Tags as chips. Enter, comma or leaving the field adds the word; Backspace on an empty field removes the last chip.
   Words that do not exist yet are created by the server when the content is saved. */
import { computed, ref, useId } from 'vue'
import AIcon from './AIcon'

const props = withDefaults(defineProps<{ suggestions?: string[]; max?: number; placeholder?: string; label?: string }>(), { suggestions: () => [], max: 20, placeholder: '输入后按回车', label: '标签' })
const model = defineModel<string[]>({ required: true })
const text = ref('')
const listId = useId()
const open = ref(false)
const sel = ref(-1)
const shown = computed(() => {
  const q = text.value.trim().toLowerCase()
  return props.suggestions.filter((s) => !model.value.some((m) => m.toLowerCase() === s.toLowerCase()) && (!q || s.toLowerCase().includes(q))).slice(0, 8)
})

function add(raw: string): void {
  const word = raw.trim().replace(/^#/, '').slice(0, 40)
  if (!word || model.value.length >= props.max) { text.value = ''; return }
  if (!model.value.some((m) => m.toLowerCase() === word.toLowerCase())) model.value = [...model.value, word]
  text.value = ''
  sel.value = -1
}
function remove(i: number): void { model.value = model.value.filter((_, k) => k !== i) }
function onKey(e: KeyboardEvent): void {
  if (e.key === 'Enter' || e.key === ',' || e.key === '，') {
    e.preventDefault()
    add(sel.value >= 0 && shown.value[sel.value] ? (shown.value[sel.value] as string) : text.value)
  } else if (e.key === 'Backspace' && !text.value && model.value.length) remove(model.value.length - 1)
  else if (e.key === 'ArrowDown' && shown.value.length) { e.preventDefault(); open.value = true; sel.value = (sel.value + 1) % shown.value.length }
  else if (e.key === 'ArrowUp' && shown.value.length) { e.preventDefault(); sel.value = (sel.value - 1 + shown.value.length) % shown.value.length }
  else if (e.key === 'Escape') open.value = false
}
</script>

<template>
  <div class="adm-tags input" @click="($refs.field as HTMLInputElement)?.focus()">
    <span v-for="(t, i) in model" :key="t" class="tag tag--sky">{{ t }}<button type="button" class="adm-tags__x" :aria-label="`移除${t}`" @click.stop="remove(i)"><AIcon name="close" /></button></span>
    <input ref="field" v-model="text" class="adm-tags__input" :placeholder="model.length ? '' : placeholder" :aria-label="label" role="combobox" :aria-expanded="open && shown.length > 0" :aria-controls="listId" autocomplete="off" @keydown="onKey" @focus="open = true" @blur="open = false; add(text)" @input="sel = -1">
    <ul v-if="open && shown.length" :id="listId" class="adm-tags__list" role="listbox">
      <li v-for="(s, i) in shown" :key="s" role="option" :aria-selected="i === sel" @mousedown.prevent="add(s)">{{ s }}</li>
    </ul>
  </div>
</template>
