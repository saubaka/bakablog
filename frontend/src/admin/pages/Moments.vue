<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Mood from '@/ui/components/Mood.vue'
import { site } from '@/public/state'
import { api, AdminError } from '../api/client'
import { mediaThumb } from '../api/media'
import { ago, when } from '../format'
import { VISIBILITY_LABEL } from '../labels'
import { loadTaxonomy, taxo } from '../taxonomy'
import type { AdminMoment, MomentList } from '../types'
import AIcon from '../ui/AIcon'
import { confirm } from '../ui/confirm'
import EmptyBox from '../ui/EmptyBox.vue'
import Menu from '../ui/Menu.vue'
import Modal from '../ui/Modal.vue'
import MomentForm from '../ui/MomentForm.vue'
import PageHead from '../ui/PageHead.vue'
import Pagination from '../ui/Pagination.vue'
import { toast, toastError } from '../ui/toast'
import { debounced, useLoader, useRouteQuery } from '../use'

const route = useRoute()
const router = useRouter()
const { state, set } = useRouteQuery({ trashed: '', visibility: '', mood: '', tag: '', month: '', q: '', page: '1' })
const search = ref(state.value.q)
const composer = ref<InstanceType<typeof MomentForm> | null>(null)
const editing = ref<AdminMoment | null>(null)
const selected = ref<Set<number>>(new Set())
const { data, loading, error, reload } = useLoader((signal) => api.get<MomentList>('/moments', {
  trashed: state.value.trashed, visibility: state.value.visibility, mood: state.value.mood, tag: state.value.tag, month: state.value.month, q: state.value.q, page: state.value.page, per: 15,
}, signal), () => state.value)

onMounted(async () => {
  void loadTaxonomy()
  if (route.query.compose) { await nextTick(); composer.value?.focus() }
})
watch(() => route.query.edit, async (id) => {
  if (!id) return
  try { editing.value = await api.get<AdminMoment>(`/moments/${id}`) } catch { /* it was removed meanwhile */ }
}, { immediate: true })
watch(data, () => { selected.value = new Set() })
watch(() => state.value.q, (v) => { search.value = v })
const applySearch = debounced((v: string) => set({ q: v.trim() }), 350)
const trashView = computed(() => state.value.trashed === '1')
const allChecked = computed(() => !!data.value?.items.length && data.value.items.every((m) => selected.value.has(m.id)))
const toggle = (id: number): void => { const s = new Set(selected.value); if (s.has(id)) s.delete(id); else s.add(id); selected.value = s }
const toggleAll = (on: boolean): void => { selected.value = on ? new Set(data.value?.items.map((m) => m.id) ?? []) : new Set() }

function closeEdit(): void { editing.value = null; if (route.query.edit) void router.replace({ path: route.path, query: { ...route.query, edit: undefined } }) }
async function saved(): Promise<void> { closeEdit(); await reload() }

async function act(fn: () => Promise<unknown>, done: string): Promise<void> {
  try { await fn(); toast(done); await reload() } catch (e) { toastError(e instanceof AdminError ? e.message : '没有成功，请再试一次。') }
}
async function trash(m: AdminMoment): Promise<void> {
  if (await confirm({ title: '移入回收站？', text: '这条动态会从前台消失，30 天内可以恢复。', confirm: '移入回收站', danger: true })) await act(() => api.del(`/moments/${m.id}`), '已移入回收站。')
}
const restore = (m: AdminMoment) => act(() => api.post(`/moments/${m.id}/restore`), '已恢复。')
async function purge(m: AdminMoment): Promise<void> {
  if (await confirm({ title: '永久删除？', text: '这条动态会被彻底删除，不能再恢复。', confirm: '永久删除', danger: true })) await act(() => api.del(`/moments/${m.id}/purge`), '已永久删除。')
}
const duplicate = (m: AdminMoment) => act(() => api.post(`/moments/${m.id}/duplicate`), '已复制为一条私密动态。')
const pin = (m: AdminMoment) => act(() => api.patch(`/moments/${m.id}`, { pinned: !m.pinned }), m.pinned ? '已取消置顶。' : '已置顶。')

async function batch(action: string): Promise<void> {
  if ((action === 'trash' || action === 'purge') && !(await confirm({ title: action === 'purge' ? `永久删除 ${selected.value.size} 条？` : `把 ${selected.value.size} 条移入回收站？`, text: action === 'purge' ? '它们会被彻底删除，不能再恢复。' : '30 天内可以恢复。', confirm: action === 'purge' ? '永久删除' : '移入回收站', danger: true }))) return
  await act(() => api.post('/moments/batch', { ids: [...selected.value], action }), '已处理。')
}
const months = computed(() => { const out: string[] = []; const d = new Date(); for (let i = 0; i < 18; i += 1) { out.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`); d.setMonth(d.getMonth() - 1) } return out })
</script>

<template>
  <div>
    <PageHead title="动态" sub="碎碎念、照片、链接，想到什么发什么。" />

    <section v-if="!trashView" class="adm-card adm-compose" aria-label="发布动态">
      <MomentForm ref="composer" @saved="reload" />
    </section>

    <div class="adm-tabs" role="tablist" aria-label="动态范围">
      <button class="tab" type="button" role="tab" :aria-selected="!trashView" @click="set({ trashed: '' })">全部<span class="n">{{ data?.counts.all ?? '' }}</span></button>
      <button class="tab" type="button" role="tab" :aria-selected="trashView" @click="set({ trashed: '1' })">回收站<span class="n">{{ data?.counts.trashed ?? '' }}</span></button>
    </div>
    <div class="adm-toolbar">
      <div class="searchfield"><AIcon name="search" /><input v-model="search" class="input" type="search" placeholder="搜动态内容" aria-label="搜索动态" @input="applySearch(search)"></div>
      <select class="select" aria-label="可见性" :value="state.visibility" @change="set({ visibility: ($event.target as HTMLSelectElement).value })"><option value="">所有可见性</option><option value="public">公开</option><option value="unlisted">仅链接可见</option><option value="private">私密</option></select>
      <select class="select" aria-label="心情" :value="state.mood" @change="set({ mood: ($event.target as HTMLSelectElement).value })"><option value="">所有心情</option><option v-for="m in site.moods" :key="m.id" :value="m.id">{{ m.label }}</option></select>
      <select class="select" aria-label="标签" :value="state.tag" @change="set({ tag: ($event.target as HTMLSelectElement).value })"><option value="">所有标签</option><option v-for="t in taxo.tags" :key="t.id" :value="t.name">{{ t.name }}</option></select>
      <select class="select" aria-label="月份" :value="state.month" @change="set({ month: ($event.target as HTMLSelectElement).value })"><option value="">所有月份</option><option v-for="m in months" :key="m" :value="m">{{ m }}</option></select>
    </div>

    <div v-if="selected.size" class="adm-batch" role="region" aria-label="批量操作">
      <b>已选 {{ selected.size }} 条</b>
      <template v-if="trashView"><button class="btn btn--sm" type="button" @click="batch('restore')">恢复</button><button class="btn btn--sm btn--danger" type="button" @click="batch('purge')">永久删除</button></template>
      <template v-else>
        <button class="btn btn--sm" type="button" @click="batch('public')">设为公开</button><button class="btn btn--sm" type="button" @click="batch('unlisted')">仅链接可见</button><button class="btn btn--sm" type="button" @click="batch('private')">设为私密</button>
        <button class="btn btn--sm btn--danger" type="button" @click="batch('trash')"><AIcon name="a-trash" />移入回收站</button>
      </template>
      <button class="btn btn--sm btn--ghost" type="button" @click="selected = new Set()">取消选择</button>
    </div>

    <p v-if="error" class="adm-error" role="alert">{{ error.message }} <button class="text-link" type="button" @click="reload">重试</button></p>
    <div v-else-if="loading && !data" class="adm-skel-grid" aria-busy="true"><span v-for="n in 3" :key="n" class="skel adm-skel adm-skel--row" /></div>
    <template v-if="data">
      <EmptyBox v-if="!data.items.length" :title="trashView ? '回收站是空的' : '还没有动态'" :text="trashView ? '' : '在上面的发布框写下第一条吧。'" />
      <template v-else>
        <label class="check adm-checkall"><input type="checkbox" :checked="allChecked" @change="toggleAll(($event.target as HTMLInputElement).checked)"><span class="check__box"><AIcon name="check" /></span>选择本页全部</label>
        <ul class="adm-moments">
          <li v-for="m in data.items" :key="m.id" class="adm-card adm-moment" :class="{ 'is-pinned': m.pinned }">
            <label class="check adm-moment__pick"><input type="checkbox" :checked="selected.has(m.id)" :aria-label="`选择动态：${m.text.slice(0, 20)}`" @change="toggle(m.id)"><span class="check__box"><AIcon name="check" /></span></label>
            <div class="adm-moment__body">
              <div class="adm-moment__meta">
                <Mood :mood="m.mood" />
                <span v-if="m.pinned" class="adm-badge adm-badge--rose"><AIcon name="pin" />置顶</span>
                <span class="adm-badge" :class="m.visibility === 'public' ? 'adm-badge--ok' : ''">{{ VISIBILITY_LABEL[m.visibility] }}</span>
                <span v-if="m.scheduled" class="adm-badge adm-badge--rose">定时</span>
                <time :datetime="m.published_at" :title="when(m.published_at)">{{ ago(m.published_at) }}</time>
              </div>
              <div v-if="m.html" class="adm-moment__text prose" v-html="m.html" />
              <ul v-if="m.media.length" class="adm-moment__pics"><li v-for="p in m.media.slice(0, 9)" :key="p.id"><img :src="mediaThumb(p as never, 480)" :alt="p.alt_override || p.alt || ''" :style="{ backgroundColor: p.color }" loading="lazy"></li></ul>
              <p v-if="m.link_card" class="adm-moment__link"><AIcon name="a-link" />{{ m.link_card.title || m.link_card.url }}<small> · {{ m.link_card.domain }}</small></p>
              <p v-if="m.tags.length" class="adm-moment__tags"><span v-for="t in m.tags" :key="t.id" class="tag tag--sky">{{ t.name }}</span></p>
            </div>
            <Menu :label="`这条动态的操作`" icon="more" icon-only>
              <template v-if="!m.deleted_at">
                <button role="menuitem" type="button" @click="editing = m"><AIcon name="a-edit" />编辑</button>
                <button role="menuitem" type="button" @click="pin(m)"><AIcon name="pin" />{{ m.pinned ? '取消置顶' : '置顶' }}</button>
                <button role="menuitem" type="button" @click="duplicate(m)"><AIcon name="copy" />复制为新动态</button>
                <a role="menuitem" :href="m.url" target="_blank" rel="noopener"><AIcon name="external" />在前台打开</a>
                <button role="menuitem" type="button" @click="trash(m)"><AIcon name="a-trash" />移入回收站</button>
              </template>
              <template v-else>
                <button role="menuitem" type="button" @click="restore(m)"><AIcon name="a-undo" />恢复</button>
                <button role="menuitem" type="button" @click="purge(m)"><AIcon name="a-trash" />永久删除</button>
              </template>
            </Menu>
          </li>
        </ul>
        <Pagination :page="data.page" :pages="data.pages" @go="(n) => set({ page: String(n) }, { keepPage: true })" />
      </template>
    </template>

    <Modal :open="editing !== null" title="编辑动态" wide @close="closeEdit">
      <MomentForm v-if="editing" :moment="editing" compact @saved="saved" @cancel="closeEdit" />
    </Modal>
  </div>
</template>
