<script setup lang="ts">
/* The rendered article next to the source: sent to the server's own Markdown pipeline (the same one that publishes), so what is shown here
   is what visitors will get, including warnings about missing pictures. */
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { labelTasks, markScrollable } from '@/shared/prose'
import { api } from '../api/client'
import { debounced } from '../use'

const props = withDefaults(defineProps<{ markdown: string; profile?: 'post' | 'moment' }>(), { profile: 'post' })
const emit = defineEmits<{ result: [r: { words: number; minutes: number; summary: string; toc: { id: string; text: string; level: number }[] }] }>()
const html = ref('')
const warnings = ref<string[]>([])
const busy = ref(false)
const failed = ref(false)
const box = ref<HTMLElement | null>(null)
const scrollable = ref(false)         // a region that scrolls must be reachable with the keyboard (it is a tab stop only while it really scrolls)
let seq = 0

const render = debounced(async () => {
  const mine = ++seq
  busy.value = true
  try {
    const r = await api.post<{ html: string; toc: { id: string; text: string; level: number }[]; summary: string; word_count: number; reading_minutes: number; warnings: string[] }>('/markdown/preview', { text: props.markdown, profile: props.profile })
    if (mine !== seq) return
    html.value = r.html
    warnings.value = r.warnings
    failed.value = false
    emit('result', { words: r.word_count, minutes: r.reading_minutes, summary: r.summary, toc: r.toc })
  } catch {
    if (mine === seq) failed.value = true
  } finally {
    if (mine === seq) busy.value = false
  }
}, 450)

watch(() => props.markdown, () => render(), { immediate: true })
/* the server's HTML has unlabelled task checkboxes and code blocks that may scroll sideways: the same fixes the public page makes */
function enhance(): void {
  if (!box.value) return
  labelTasks(box.value)
  markScrollable(box.value)
  scrollable.value = box.value.scrollHeight > box.value.clientHeight + 1
}
watch(html, () => { void nextTick(enhance) })
let ro: ResizeObserver | null = null
onMounted(() => { if ('ResizeObserver' in window && box.value) { ro = new ResizeObserver(enhance); ro.observe(box.value) } })
onBeforeUnmount(() => { render.cancel(); seq += 1; ro?.disconnect() })
function setScroll(ratio: number): void { const el = box.value; if (el) el.scrollTop = ratio * (el.scrollHeight - el.clientHeight) }
defineExpose({ setScroll })
</script>

<template>
  <div class="adm-preview">
    <p v-if="failed" class="adm-error" role="alert">预览暂时没有刷新成功，下次输入时会再试。</p>
    <ul v-if="warnings.length" class="adm-preview__warn" role="status"><li v-for="w in warnings" :key="w">{{ w }}</li></ul>
    <div ref="box" class="adm-preview__scroll" role="region" aria-label="文章预览" :tabindex="scrollable ? 0 : undefined">
      <p v-if="!markdown.trim()" class="adm-preview__empty">在左边写点什么，这里就会显示文章真正的样子。</p>
      <div v-else class="prose adm-preview__prose" :aria-busy="busy" v-html="html" />
    </div>
  </div>
</template>
