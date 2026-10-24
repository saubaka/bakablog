<script setup lang="ts">
defineProps<{ label: string; hint?: string; disabled?: boolean }>()
const model = defineModel<boolean>({ required: true })
</script>

<template>
  <label class="switch adm-switch">
    <input v-model="model" type="checkbox" role="switch" :disabled="disabled">
    <span class="switch__track" aria-hidden="true" />
    <span class="adm-switch__text"><b>{{ label }}</b><small v-if="hint">{{ hint }}</small></span>
  </label>
</template>
