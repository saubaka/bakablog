<script setup lang="ts">
import { vFx } from '@/fx/directive'
import Icon from '@/ui/components/Icon'

defineProps<{ title: string; items: { icon: string; text: string }[] }>()
</script>

<template>
  <aside class="note note--tilt" v-fx="'rise'" :aria-label="title">
    <span class="tape tape--dots tape--right" />
    <h3>{{ title }}</h3>
    <ul>
      <li v-for="(it, i) in items" :key="i"><Icon :name="it.icon" />{{ it.text }}</li>
    </ul>
  </aside>
</template>
