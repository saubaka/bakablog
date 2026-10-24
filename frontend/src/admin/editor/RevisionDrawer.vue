<script setup lang="ts">
/* Version history of a post or page: the last 20 saved versions, a comparison with what is in the editor now, and "restore this one". */
import { computed, ref, watch } from 'vue'
import { api, AdminError } from '../api/client'
import { ago, when } from '../format'
import type { Revision, RevisionDetail } from '../types'
import Drawer from '../ui/Drawer.vue'
import { toastError } from '../ui/toast'
import { lineDiff, withContext } from './linediff'

const props = defineProps<{ open: boolean; base: string; currentMarkdown: string; currentTitle: string }>()
const emit = defineEmits<{ close: []; restore: [id: number] }>()
const items = ref<Revision[]>([])
const loading = ref(false)
const shown = ref<RevisionDetail | null>(null)

watch(() => props.open, async (o) => {
  if (!o) { shown.value = null; return }
  loading.value = true
  try { items.value = (await api.get<{ items: Revision[] }>(`${props.base}/revisions`)).items } catch (e) { toastError(e instanceof AdminError ? e.message : '版本历史加载失败。') } finally { loading.value = false }
})

async function view(r: Revision): Promise<void> {
  try { shown.value = await api.get<RevisionDetail>(`${props.base}/revisions/${r.id}`) } catch (e) { toastError(e instanceof AdminError ? e.message : '这个版本打不开。') }
}
const diff = computed(() => {
  if (!shown.value) return null
  const old = String(shown.value.snapshot.content_md ?? '')
  const lines = lineDiff(old, props.currentMarkdown)
  return lines ? withContext(lines) : null
})
const changes = computed(() => (diff.value ?? []).filter((l) => l.kind === 'add' || l.kind === 'del').length)
</script>

<template>
  <Drawer :open="open" title="版本历史" @close="emit('close')">
    <p class="adm-hint">每次保存都会留一个版本，最多保留最近 20 个。下面的对比是“那个版本 → 编辑器里现在的内容”。</p>
    <p v-if="loading" role="status">正在加载……</p>
    <ol v-if="!shown" class="adm-revs">
      <li v-for="(r, i) in items" :key="r.id">
        <button class="adm-revs__row" type="button" @click="view(r)"><b>{{ r.title || '（无标题）' }}</b><span>{{ when(r.created_at) }} · {{ ago(r.created_at) }}</span><small>{{ r.length }} 个字符<template v-if="i === 0"> · 最新</template></small></button>
      </li>
      <li v-if="!items.length && !loading" class="adm-hint">还没有历史版本。</li>
    </ol>
    <template v-else>
      <button class="text-link" type="button" @click="shown = null">← 回到列表</button>
      <h3 class="adm-revs__title">{{ String(shown.snapshot.title ?? '') }} <small>{{ when(shown.created_at) }}</small></h3>
      <p v-if="shown.snapshot.title !== currentTitle" class="adm-hint">标题现在是「{{ currentTitle }}」。</p>
      <p v-if="diff === null" class="adm-hint">内容太长，不做逐行对比；恢复后可以自己看。</p>
      <p v-else-if="!changes" class="adm-hint">正文和现在完全一样。</p>
      <div v-else class="adm-diff" role="region" aria-label="与现在的差异" tabindex="0">
        <template v-for="(l, i) in diff" :key="i">
          <p v-if="l.kind === 'gap'" class="adm-diff__gap">… 中间 {{ l.count }} 行没有变化 …</p>
          <p v-else class="adm-diff__line" :class="`is-${l.kind}`"><span aria-hidden="true">{{ l.kind === 'add' ? '+' : l.kind === 'del' ? '−' : ' ' }}</span>{{ l.text || ' ' }}</p>
        </template>
      </div>
    </template>
    <template v-if="shown" #footer>
      <button class="btn btn--ghost" type="button" @click="shown = null">返回</button>
      <button class="btn btn--fill" type="button" @click="emit('restore', shown.id)">恢复到这个版本</button>
    </template>
  </Drawer>
</template>
