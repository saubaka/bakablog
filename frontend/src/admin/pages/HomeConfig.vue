<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { fetchSite } from '@/public/data'
import { site as publicSite } from '@/public/state'
import type { HomeBlock } from '@/shared/types'
import { api, AdminError } from '../api/client'
import type { HomeAdmin } from '../types'
import AIcon from '../ui/AIcon'
import { confirm } from '../ui/confirm'
import PageHead from '../ui/PageHead.vue'
import PreviewFrame from '../ui/PreviewFrame.vue'
import Segmented from '../ui/Segmented.vue'
import { useSortable } from '../ui/sortable'
import { toast, toastError } from '../ui/toast'
import { debounced, useLeaveGuard } from '../use'
import BlockForm from './home/BlockForm.vue'
import { BLOCKS, defaultConfig, META } from './home/blocks'

interface Row { key: number; type: string; enabled: boolean; config: Record<string, any>; open: boolean }   // eslint-disable-line @typescript-eslint/no-explicit-any
let key = 1
const rows = ref<Row[]>([])
const original = ref('')
const customized = ref(false)
const loading = ref(true)
const busy = ref(false)
const errors = reactive<Record<string, Record<string, string>>>({})
const pane = ref<'edit' | 'view'>('edit')
const preview = ref<HomeBlock[] | null>(null)
const stale = ref(false)

const body = (): { blocks: { type: string; enabled: boolean; config: Record<string, unknown> }[] } => ({ blocks: rows.value.map(({ type, enabled, config }) => ({ type, enabled, config: JSON.parse(JSON.stringify(config)) as Record<string, unknown> })) })
const serial = (): string => JSON.stringify(body())
const dirty = computed(() => !loading.value && serial() !== original.value)
useLeaveGuard(() => dirty.value)
const sort = useSortable(() => rows.value, (n) => { rows.value = n })

function load(h: HomeAdmin): void {
  const have = new Set(h.blocks.map((b) => b.type))
  const all = [...h.blocks.map((b) => ({ type: b.type, enabled: b.enabled, config: b.config })), ...BLOCKS.filter((b) => !have.has(b.type)).map((b) => ({ type: b.type, enabled: false, config: defaultConfig(b.type) }))]
  rows.value = all.map((b) => ({ key: key++, type: b.type, enabled: b.enabled, config: JSON.parse(JSON.stringify(b.config)) as Record<string, unknown>, open: false }))
  customized.value = h.customized
  original.value = serial()
}
onMounted(async () => {
  try { load(await api.get<HomeAdmin>('/home')); await refreshPreview() } catch (e) { toastError(e instanceof AdminError ? e.message : '首页设置加载失败。') } finally { loading.value = false }
})

/* the picture on the right: ask the server what visitors would see for this unsaved layout */
let ticket = 0
async function refreshPreview(): Promise<void> {
  const mine = ++ticket
  try {
    const out = await api.post<{ blocks: HomeBlock[] }>('/home/preview', body())
    if (mine !== ticket) return
    preview.value = out.blocks
    stale.value = false
  } catch { if (mine === ticket) stale.value = true }
}
const queue = debounced(() => { void refreshPreview() }, 450)
watch(rows, () => { if (!loading.value) queue() }, { deep: true })

async function save(): Promise<void> {
  busy.value = true
  Object.keys(errors).forEach((k) => delete errors[k])
  try {
    const out = await api.put<HomeAdmin>('/home', body())
    load(out)
    customized.value = true
    toast('首页已保存。')
    try { const s = await fetchSite(); publicSite.value = s } catch { /* the saved page is what counts */ }
  } catch (e) {
    if (e instanceof AdminError) {
      for (const [path, msg] of Object.entries(e.fields)) {
        const m = /^blocks\.(\d+)\.config\.(.+)$/.exec(path)
        const row = m ? rows.value[Number(m[1])] : undefined
        if (m && row) { (errors[row.type] ??= {})[m[2] as string] = msg; row.open = true }
      }
      toastError(e.message)
    } else toastError('保存没有成功。')
  } finally { busy.value = false }
}
async function reset(): Promise<void> {
  if (!(await confirm({ title: '恢复默认首页？', text: '模块的顺序、开关和文字都会回到出厂的样子，你改过的会丢掉。', confirm: '恢复默认', danger: true }))) return
  try { await api.post('/home/reset'); load(await api.get<HomeAdmin>('/home')); toast('已恢复默认首页。'); await refreshPreview() } catch (e) { toastError(e instanceof AdminError ? e.message : '没有成功。') }
}
const tabs = [{ value: 'edit' as const, label: '编辑' }, { value: 'view' as const, label: '预览' }]
</script>

<template>
  <div>
    <PageHead title="首页配置" sub="首页由 5 个模块组成：拖动调整顺序，开关决定显不显示。右边是未保存也能看到的预览。">
      <button class="btn btn--ghost" type="button" :disabled="!customized" @click="reset">恢复默认</button>
      <button class="btn btn--fill" type="button" :disabled="busy || !dirty" @click="save"><AIcon name="a-save" />保存首页</button>
    </PageHead>
    <p v-if="loading" class="adm-boot" role="status">正在加载首页设置……</p>
    <div v-else class="adm-homecfg" :data-pane="pane">
      <Segmented v-model="pane" class="adm-homecfg__tabs" label="编辑或预览" :options="tabs" />
      <section class="adm-homecfg__pane" aria-label="首页模块">
        <ul class="adm-sortlist">
          <li v-for="(r, i) in rows" :key="r.key" class="adm-card adm-navrow" :class="{ 'is-dragging': sort.dragging.value === i, 'is-off': !r.enabled }" data-sort-row>
            <div class="adm-navrow__head">
              <button class="adm-grip" type="button" :aria-label="`拖动调整「${META[r.type]?.name}」的位置`" v-bind="sort.handle(i)"><AIcon name="a-grip" /></button>
              <span class="adm-sortrow__ico"><AIcon :name="META[r.type]?.icon ?? 'link'" /></span>
              <span class="adm-sortrow__main"><b>{{ META[r.type]?.name ?? r.type }}</b><small>{{ META[r.type]?.help }}</small></span>
              <label class="switch"><input v-model="r.enabled" type="checkbox" role="switch" :aria-label="`显示「${META[r.type]?.name}」`"><span class="switch__track" aria-hidden="true" /></label>
              <button class="btn btn--sm btn--ghost" type="button" :aria-expanded="r.open" @click="r.open = !r.open"><AIcon name="a-edit" />{{ r.open ? '收起' : '设置' }}</button>
            </div>
            <div v-if="r.open" class="adm-navrow__edit"><BlockForm :type="r.type" :config="r.config" :errors="errors[r.type] ?? {}" /></div>
          </li>
        </ul>
        <p class="sr-only" role="status" aria-live="polite">{{ sort.announce.value }}</p>
      </section>
      <section class="adm-homecfg__preview" aria-label="预览">
        <PreviewFrame :site="publicSite" :home="preview" :stale="stale" />
      </section>
    </div>
  </div>
</template>
