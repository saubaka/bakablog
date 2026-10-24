<script setup lang="ts" generic="T extends string | number">
/* One choice out of a few, as a row of buttons (radio group semantics). */
defineProps<{ options: { value: T; label: string; hint?: string }[]; label: string }>()
const model = defineModel<T>({ required: true })
</script>

<template>
  <div class="adm-seg" role="radiogroup" :aria-label="label">
    <button v-for="o in options" :key="String(o.value)" class="adm-seg__item" type="button" role="radio" :aria-checked="model === o.value" :title="o.hint" @click="model = o.value">{{ o.label }}</button>
  </div>
</template>
