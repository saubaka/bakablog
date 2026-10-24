<script setup lang="ts">
/* The author's round picture: the uploaded avatar, else the first letter of the name. */
import { computed } from 'vue'
import { site } from '../state'

defineProps<{ large?: boolean }>()
const avatar = computed(() => site.value.author.avatar)
const initial = computed(() => Array.from(site.value.author.name.trim())[0] ?? '')
</script>

<template>
  <span class="avatar" :class="{ 'avatar--lg': large }">
    <img v-if="avatar" class="avatar__img" :src="avatar.src" :srcset="avatar.srcset || undefined" :sizes="large ? '88px' : '44px'" :alt="''" :width="avatar.width" :height="avatar.height" loading="lazy" decoding="async">
    <b v-else class="avatar__initial" aria-hidden="true">{{ initial }}</b>
  </span>
</template>
