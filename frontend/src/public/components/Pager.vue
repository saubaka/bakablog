<script setup lang="ts">
/* Page numbers with gaps (1 … 4 5 6 … 12). Every number is a real link, so paging works in a new tab and without scripts. */
import { computed } from 'vue'
import type { RouteLocationRaw } from 'vue-router'
import Icon from '@/ui/components/Icon'

const props = defineProps<{ page: number; pages: number; to: (page: number) => RouteLocationRaw }>()

const items = computed(() => {
  const { page, pages } = props
  const keep = new Set<number>([1, pages, page, page - 1, page + 1])
  if (page <= 3) { keep.add(2); keep.add(3); keep.add(4) }
  if (page >= pages - 2) { keep.add(pages - 1); keep.add(pages - 2); keep.add(pages - 3) }
  const sorted = [...keep].filter((n) => n >= 1 && n <= pages).sort((a, b) => a - b)
  const out: (number | null)[] = []
  sorted.forEach((n, i) => {
    const before = sorted[i - 1]
    if (before !== undefined && n - before > 1) out.push(null)
    out.push(n)
  })
  return out
})
</script>

<template>
  <nav v-if="pages > 1" v-fx="'fade'" class="pager" aria-label="分页">
    <RouterLink v-if="page > 1" :to="to(page - 1)" rel="prev" aria-label="上一页"><Icon name="arrow-l" /></RouterLink>
    <template v-for="(n, i) in items" :key="n ?? `gap${i}`">
      <span v-if="n === null" class="is-gap" aria-hidden="true">…</span>
      <RouterLink v-else :to="to(n)" :aria-current="n === page ? 'page' : undefined" :aria-label="`第 ${n} 页`">{{ n }}</RouterLink>
    </template>
    <RouterLink v-if="page < pages" :to="to(page + 1)" rel="next" aria-label="下一页"><Icon name="arrow-r" /></RouterLink>
  </nav>
</template>
