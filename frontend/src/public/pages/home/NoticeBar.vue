<script setup lang="ts">
import { vFx } from '@/fx/directive'
import Icon from '@/ui/components/Icon'

defineProps<{ text: string }>()
</script>

<template>
  <div class="wrap">
    <p class="notice" v-fx="'fade'" role="note"><Icon name="info" />{{ text }}</p>
  </div>
</template>
