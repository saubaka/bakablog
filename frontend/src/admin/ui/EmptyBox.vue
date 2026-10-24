<script setup lang="ts">
defineProps<{ title: string; text?: string }>()
</script>

<template>
  <div class="empty adm-empty">
    <strong>{{ title }}</strong>
    <span v-if="text">{{ text }}</span>
    <slot />
  </div>
</template>
