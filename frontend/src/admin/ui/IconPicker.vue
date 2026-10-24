<script setup lang="ts">
/* Pick one of the hand-drawn icons (the same vocabulary the server accepts for stickers). */
import { ICONS } from '@/public/icons'
import AIcon from './AIcon'

defineProps<{ label?: string }>()
const model = defineModel<string | null>({ required: true })
const names = [...ICONS].filter((n) => !['close', 'menu', 'more', 'arrow-r', 'arrow-l', 'arrow-u', 'arrow-d', 'sliders', 'grid', 'rows', 'check', 'copy', 'search', 'external'].includes(n))
</script>

<template>
  <div class="adm-icons" role="radiogroup" :aria-label="label ?? '图标'">
    <button class="adm-icons__b" type="button" role="radio" :aria-checked="!model" aria-label="没有图标" title="没有图标" @click="model = null"><AIcon name="a-minus" /></button>
    <button v-for="n in names" :key="n" class="adm-icons__b" type="button" role="radio" :aria-checked="model === n" :aria-label="n" :title="n" @click="model = n"><AIcon :name="n" /></button>
  </div>
</template>
