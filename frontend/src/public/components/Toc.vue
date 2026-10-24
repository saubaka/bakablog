<script setup lang="ts">
/* Table of contents: a sticky list on wide screens (the indicator slides to the heading being read) and the same list in a drawer on phones. */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Icon from '@/ui/components/Icon'
import type { TocEntry } from '@/shared/types'
import { useActiveHeading } from './useActiveHeading'
import BottomSheet from '../layout/BottomSheet.vue'

const props = defineProps<{ entries: TocEntry[] }>()
const route = useRoute()
const router = useRouter()
const list = computed(() => props.entries.filter((e) => e.level <= 3))
const { active } = useActiveHeading(() => list.value.map((e) => e.id))
const ol = ref<HTMLElement | null>(null)
const sheet = ref(false)
const ind = ref({ y: 0, h: 0, ready: false })

function place(): void {
  const a = ol.value?.querySelectorAll<HTMLElement>('a')[active.value]
  if (a) ind.value = { y: a.offsetTop, h: a.offsetHeight, ready: true }
}
watch(active, async () => { await nextTick(); place() }, { immediate: true, flush: 'post' })

function jump(id: string): void {
  sheet.value = false
  void router.push({ path: route.path, query: route.query, hash: `#${id}` })
}
/* the phone's TOC button and the back-to-top ring share the bottom right corner: the ring moves up while the button is there */
onMounted(() => { if (list.value.length) document.documentElement.classList.add('has-toc-fab') })
onBeforeUnmount(() => document.documentElement.classList.remove('has-toc-fab'))
defineExpose({ openSheet: () => { sheet.value = true } })
</script>

<template>
  <aside v-if="list.length" class="toc" aria-label="目录">
    <h2 v-fx="'fade'"><Icon name="list" />目录</h2>
    <ol ref="ol" v-fx="'fade'">
      <i class="toc__ind" :class="{ 'is-ready': ind.ready }" :style="{ '--y': `${ind.y}px`, '--h': `${ind.h}px` }" aria-hidden="true" />
      <li v-for="(e, i) in list" :key="e.id"><a :href="`#${e.id}`" :class="[e.level === 3 ? 'lv3' : '', { 'is-active': i === active }]" :aria-current="i === active ? 'location' : undefined" @click.prevent="jump(e.id)">{{ e.text }}</a></li>
    </ol>
  </aside>
  <button v-if="list.length" class="btn btn--fill toc-fab" type="button" @click="sheet = true"><Icon name="list" />目录</button>
  <BottomSheet v-if="list.length" :open="sheet" label="目录" @close="sheet = false">
    <h2>目录</h2>
    <ol>
      <li v-for="e in list" :key="e.id"><a :href="`#${e.id}`" :class="e.level === 3 ? 'lv3' : ''" @click.prevent="jump(e.id)">{{ e.text }}</a></li>
    </ol>
  </BottomSheet>
</template>
