<script setup lang="ts">
import { computed } from 'vue'
import { stampOf } from '../fmt'

const props = defineProps<{ iso: string; small?: boolean }>()
const s = computed(() => stampOf(props.iso))
</script>

<template>
  <div class="stamp" :class="{ 'stamp--sm': small }" aria-hidden="true"><b>{{ s.day }}</b><small>{{ s.mon }}</small></div>
</template>
