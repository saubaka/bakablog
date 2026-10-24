<script setup lang="ts">
defineProps<{ title: string; sub?: string }>()
</script>

<template>
  <header class="adm-pagehead">
    <div>
      <h1>{{ title }}</h1>
      <p v-if="sub">{{ sub }}</p>
    </div>
    <div v-if="$slots.default" class="adm-pagehead__actions"><slot /></div>
  </header>
</template>
