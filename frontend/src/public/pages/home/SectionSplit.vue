<script setup lang="ts">
/* The page's recurring section: a narrow label column (title, one line of text, optional link) and the content next to it. */
import FxText from '@/fx/FxText.vue'
import { vFx } from '@/fx/directive'

defineProps<{ id?: string; title: string; intro?: string }>()
</script>

<template>
  <section :id="id" class="section">
    <div class="wrap split">
      <div class="split__label">
        <FxText tag="h2" :text="title" />
        <p v-if="intro" v-fx="'fade'">{{ intro }}</p>
        <slot name="label" />
      </div>
      <div class="split__body"><slot /></div>
    </div>
  </section>
</template>
