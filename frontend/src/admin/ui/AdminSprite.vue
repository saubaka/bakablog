<script setup lang="ts">
import Sprite from '@/ui/components/Sprite.vue'
import adminSprite from './admin-sprite.svg?raw'
</script>

<template>
  <Sprite />
  <div class="sprite" aria-hidden="true" v-html="adminSprite" />
</template>
