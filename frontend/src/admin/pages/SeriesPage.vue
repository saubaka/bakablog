<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { api, AdminError } from '../api/client'
import CoverPicker from '../editor/CoverPicker.vue'
import type { AdminSeries } from '../types'
import AIcon from '../ui/AIcon'
import { confirm } from '../ui/confirm'
import EmptyBox from '../ui/EmptyBox.vue'
import Field from '../ui/Field.vue'
import Modal from '../ui/Modal.vue'
import PageHead from '../ui/PageHead.vue'
import Segmented from '../ui/Segmented.vue'
import { useSortable } from '../ui/sortable'
import { toast, toastError } from '../ui/toast'
import { useSubmit } from '../use'
import type { Media } from '@/shared/types'

interface SeriesPost { id: number; title: string; slug: string; status: string; order: number }
const list = ref<AdminSeries[]>([])
const loading = ref(true)
const editing = ref<AdminSeries | 'new' | null>(null)
const form = reactive({ title: '', slug: '', description: '', status: 'ongoing' as 'ongoing' | 'finished', cover: null as Media | null })
const { busy, fields, run } = useSubmit()
const ordering = ref<AdminSeries | null>(null)
const posts = ref<SeriesPost[]>([])
const orderChanged = ref(false)
const sort = useSortable(() => posts.value, (n) => { posts.value = n; orderChanged.value = true })

async function load(): Promise<void> {
  loading.value = true
  try { list.value = (await api.get<{ items: AdminSeries[] }>('/taxonomy/series')).items } catch (e) { toastError(e instanceof AdminError ? e.message : '系列加载失败。') } finally { loading.value = false }
}
onMounted(load)

function open(s: AdminSeries | 'new'): void {
  editing.value = s
  Object.assign(form, s === 'new' ? { title: '', slug: '', description: '', status: 'ongoing', cover: null } : { title: s.title, slug: s.slug, description: s.description, status: s.status, cover: s.cover })
}
async function save(): Promise<void> {
  const target = editing.value
  try {
    await run(async () => {
      const body = { title: form.title.trim(), description: form.description.trim(), status: form.status, cover_media_id: form.cover?.id ?? null, ...(form.slug.trim() ? { slug: form.slug.trim() } : {}) }
      if (target === 'new') await api.post('/taxonomy/series', body)
      else if (target) await api.patch(`/taxonomy/series/${target.id}`, body)
    })
    toast('系列已保存。')
    editing.value = null
    await load()
  } catch (e) { if (!(e instanceof AdminError && e.status === 422)) toastError(e instanceof AdminError ? e.message : '保存没有成功。') }
}
async function remove(s: AdminSeries): Promise<void> {
  if (!(await confirm({ title: `删除系列「${s.title}」？`, text: `里面的 ${s.count} 篇文章会保留，只是不再属于这个系列。`, confirm: '删除系列', danger: true }))) return
  try { await api.del(`/taxonomy/series/${s.id}`); toast('系列已删除。'); await load() } catch (e) { toastError(e instanceof AdminError ? e.message : '删除没有成功。') }
}
async function openOrder(s: AdminSeries): Promise<void> {
  try { posts.value = (await api.get<{ items: SeriesPost[] }>(`/taxonomy/series/${s.id}/posts`)).items; orderChanged.value = false; ordering.value = s } catch (e) { toastError(e instanceof AdminError ? e.message : '文章顺序加载失败。') }
}
async function saveOrder(): Promise<void> {
  if (!ordering.value) return
  try { await api.put(`/taxonomy/series/${ordering.value.id}/order`, { post_ids: posts.value.map((p) => p.id) }); toast('顺序已保存。'); ordering.value = null; await load() } catch (e) { toastError(e instanceof AdminError ? e.message : '保存没有成功。') }
}
</script>

<template>
  <div>
    <PageHead title="系列" sub="把几篇文章连成一串：前台文章底部会显示“第几篇 / 共几篇”和目录。">
      <button class="btn btn--fill" type="button" @click="open('new')"><AIcon name="a-plus" />新建系列</button>
    </PageHead>
    <EmptyBox v-if="!loading && !list.length" title="还没有系列" text="写一组连载时，先在这里建一个，再到文章编辑页的“整理”里选它。" />
    <div v-else class="adm-cards">
      <article v-for="s in list" :key="s.id" class="adm-card adm-series">
        <div class="adm-series__head"><h2>{{ s.title }}</h2><span class="adm-badge" :class="s.status === 'ongoing' ? 'adm-badge--rose' : 'adm-badge--ok'">{{ s.status === 'ongoing' ? '连载中' : '已完结' }}</span></div>
        <p>{{ s.description || '（没有说明）' }}</p>
        <small>/series/{{ s.slug }} · {{ s.count }} 篇</small>
        <div class="adm-series__actions">
          <button class="btn btn--sm" type="button" @click="openOrder(s)"><AIcon name="list" />调整文章顺序</button>
          <button class="btn btn--sm btn--ghost" type="button" @click="open(s)"><AIcon name="a-edit" />编辑</button>
          <button class="icon-btn icon-btn--ghost" type="button" :aria-label="`删除系列：${s.title}`" @click="remove(s)"><AIcon name="a-trash" /></button>
        </div>
      </article>
    </div>

    <Modal :open="editing !== null" :title="editing === 'new' ? '新建系列' : '编辑系列'" @close="editing = null">
      <form class="adm-form" @submit.prevent="save">
        <Field v-slot="{ id }" label="标题" required :error="fields.title"><input :id="id" v-model="form.title" class="input" maxlength="120" data-autofocus></Field>
        <Field v-slot="{ id }" label="别名" :error="fields.slug" hint="留空自动生成。"><input :id="id" v-model="form.slug" class="input" spellcheck="false"></Field>
        <Field v-slot="{ id }" label="说明" :error="fields.description"><textarea :id="id" v-model="form.description" class="textarea" rows="3" maxlength="1000" /></Field>
        <Field label="状态"><Segmented v-model="form.status" label="连载状态" :options="[{ value: 'ongoing', label: '连载中' }, { value: 'finished', label: '已完结' }]" /></Field>
        <Field label="封面（可选）"><CoverPicker :media="form.cover" title="选择封面" @pick="(m) => (form.cover = m)" /></Field>
      </form>
      <template #footer><button class="btn btn--ghost" type="button" @click="editing = null">取消</button><button class="btn btn--fill" type="button" :disabled="busy || !form.title.trim()" @click="save">保存</button></template>
    </Modal>

    <Modal :open="ordering !== null" :title="`「${ordering?.title ?? ''}」的文章顺序`" @close="ordering = null">
      <p class="adm-hint">拖动左边的把手，或在把手上按 ↑ ↓。第一篇会显示为“第 1 篇”。</p>
      <ul class="adm-sortlist">
        <li v-for="(p, i) in posts" :key="p.id" class="adm-sortrow" :class="{ 'is-dragging': sort.dragging.value === i }" data-sort-row>
          <button class="adm-grip" type="button" :aria-label="`拖动调整「${p.title}」的位置`" v-bind="sort.handle(i)"><AIcon name="a-grip" /></button>
          <span class="adm-sortrow__no">{{ i + 1 }}</span>
          <span class="adm-sortrow__main"><b>{{ p.title }}</b><small>{{ p.status === 'published' ? '已发布' : p.status }}</small></span>
        </li>
      </ul>
      <p class="sr-only" role="status" aria-live="polite">{{ sort.announce.value }}</p>
      <template #footer><button class="btn btn--ghost" type="button" @click="ordering = null">取消</button><button class="btn btn--fill" type="button" :disabled="!orderChanged" @click="saveOrder">保存顺序</button></template>
    </Modal>
  </div>
</template>
