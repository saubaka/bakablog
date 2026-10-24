<script setup lang="ts">
import { computed } from 'vue'
import AIcon from './AIcon'

const props = defineProps<{ page: number; pages: number }>()
const emit = defineEmits<{ go: [number] }>()
const items = computed(() => {
  const { page, pages } = props
  const keep = new Set<number>([1, pages, page, page - 1, page + 1])
  if (page <= 3) for (const n of [2, 3, 4]) keep.add(n)
  if (page >= pages - 2) for (const n of [pages - 1, pages - 2, pages - 3]) keep.add(n)
  const sorted = [...keep].filter((n) => n >= 1 && n <= pages).sort((a, b) => a - b)
  const out: (number | null)[] = []
  sorted.forEach((n, i) => { const before = sorted[i - 1]; if (before !== undefined && n - before > 1) out.push(null); out.push(n) })
  return out
})
</script>

<template>
  <nav v-if="pages > 1" class="pager adm-pager" aria-label="分页">
    <button type="button" :disabled="page <= 1" aria-label="上一页" @click="emit('go', page - 1)"><AIcon name="arrow-l" /></button>
    <template v-for="(n, i) in items" :key="n ?? `g${i}`">
      <span v-if="n === null" class="is-gap" aria-hidden="true">…</span>
      <button v-else type="button" :aria-current="n === page ? 'page' : undefined" :aria-label="`第 ${n} 页`" @click="emit('go', n)">{{ n }}</button>
    </template>
    <button type="button" :disabled="page >= pages" aria-label="下一页" @click="emit('go', page + 1)"><AIcon name="arrow-r" /></button>
  </nav>
</template>
