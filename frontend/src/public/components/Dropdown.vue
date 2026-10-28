<script setup lang="ts">
/* A drop-down list drawn by the site (the browser's own <select> menu cannot be styled): a button that shows the choice and a list that opens under it.
   The button keeps the focus and points at the highlighted option (aria-activedescendant), as in the ARIA "select-only combobox".
   Keyboard: ↓ ↑ open it; ↑ ↓ Home End move; Enter / Space choose; Esc closes; Tab leaves. A press outside closes it. */
import { computed, onBeforeUnmount, ref, useId, watch } from 'vue'
import Icon from '@/ui/components/Icon'

export interface Choice { value: string; label: string }

const props = defineProps<{ modelValue: string; options: Choice[]; label: string; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const id = useId()
const root = ref<HTMLElement | null>(null)
const open = ref(false)
const active = ref(0)
let spaceDown = false

const current = computed(() => props.options.find((o) => o.value === props.modelValue) ?? props.options[0])

function show(): void {
  if (props.disabled || !props.options.length) return
  active.value = Math.max(0, props.options.findIndex((o) => o.value === props.modelValue))
  open.value = true
}
const hide = (): void => { open.value = false }
/** (Safari does not focus a button that was clicked, and the keys work on the focused button: so the click does it.) */
function toggle(e: MouseEvent): void {
  ;(e.currentTarget as HTMLElement).focus({ preventScroll: true })
  if (open.value) hide(); else show()
}

function choose(i: number): void {
  const o = props.options[i]
  if (o && o.value !== props.modelValue) emit('update:modelValue', o.value)
  hide()
}

function onKey(e: KeyboardEvent): void {
  const n = props.options.length
  if (!open.value) {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); show() }
    return                                                   // Enter and Space press the button as usual
  }
  if (e.key === 'ArrowDown') { e.preventDefault(); active.value = (active.value + 1) % n }
  else if (e.key === 'ArrowUp') { e.preventDefault(); active.value = (active.value - 1 + n) % n }
  else if (e.key === 'Home') { e.preventDefault(); active.value = 0 }
  else if (e.key === 'End') { e.preventDefault(); active.value = n - 1 }
  else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); spaceDown = e.key === ' '; choose(active.value) }
  else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); hide() }
  else if (e.key === 'Tab') hide()
}
/** A space chooses on key down; the click that the browser makes when the key comes up must not open the list again. */
function onKeyup(e: KeyboardEvent): void {
  if (e.key === ' ' && spaceDown) { e.preventDefault(); spaceDown = false }
}

/* Safari does not focus a button that was clicked, so losing focus cannot be the only way to notice a press somewhere else */
function onPress(e: Event): void {
  if (root.value && !root.value.contains(e.target as Node)) hide()
}
watch(open, (on) => {
  if (on) document.addEventListener('pointerdown', onPress, true)
  else document.removeEventListener('pointerdown', onPress, true)
})
onBeforeUnmount(() => document.removeEventListener('pointerdown', onPress, true))
</script>

<template>
  <div ref="root" class="dd" :class="{ 'is-open': open }">
    <button
      type="button" class="dd__btn" role="combobox" aria-haspopup="listbox" :aria-label="label" :aria-expanded="open" :aria-controls="open ? id : undefined"
      :aria-activedescendant="open ? `${id}-${active}` : undefined" :disabled="disabled" @click="toggle" @keydown="onKey" @keyup="onKeyup" @blur="hide"
    >
      <span class="dd__value">{{ current?.label }}</span>
      <span class="dd__chev" aria-hidden="true" />
    </button>
    <Transition name="dd">
      <ul v-if="open" :id="id" class="dd__list" role="listbox" :aria-label="label">
        <li
          v-for="(o, i) in options" :id="`${id}-${i}`" :key="o.value" class="dd__opt" :class="{ 'is-active': i === active }" role="option" :aria-selected="o.value === modelValue"
          :style="{ '--i': i }" @mousedown.prevent @mousemove="active = i" @click="choose(i)"
        >
          <span>{{ o.label }}</span>
          <Icon name="check" />
        </li>
      </ul>
    </Transition>
  </div>
</template>
