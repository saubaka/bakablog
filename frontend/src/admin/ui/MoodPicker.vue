<script setup lang="ts">
/* The ten mood stickers of a moment (the server's vocabulary, site.moods). Clicking the chosen one again clears it. */
import { site } from '@/public/state'

const model = defineModel<string | null>({ required: true })
</script>

<template>
  <div class="adm-moods" role="radiogroup" aria-label="心情">
    <button v-for="m in site.moods" :key="m.id" class="adm-mood" type="button" role="radio" :aria-checked="model === m.id" :title="m.label" @click="model = model === m.id ? null : m.id">
      <svg aria-hidden="true" focusable="false"><use :href="`#mood-${m.id}`" /></svg><span>{{ m.label }}</span>
    </button>
  </div>
</template>
