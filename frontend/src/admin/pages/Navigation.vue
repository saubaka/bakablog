<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { getJSON } from '@/shared/api'
import { site as publicSite } from '@/public/state'
import type { HomePayload, NavItem, SiteInfo } from '@/shared/types'
import { api, AdminError } from '../api/client'
import { loadSettings, saveGroup, settingsState } from '../settings'
import { loadTaxonomy, taxo } from '../taxonomy'
import type { AdminPage, ListPage, NavAdmin, NavItemAdmin, SettingsGroups } from '../types'
import AIcon from '../ui/AIcon'
import { confirm } from '../ui/confirm'
import Field from '../ui/Field.vue'
import IconPicker from '../ui/IconPicker.vue'
import PageHead from '../ui/PageHead.vue'
import PreviewFrame from '../ui/PreviewFrame.vue'
import Segmented from '../ui/Segmented.vue'
import { useSortable } from '../ui/sortable'
import { toast, toastError } from '../ui/toast'
import { useLeaveGuard } from '../use'

type Region = 'top' | 'mobile' | 'footer'
interface Row extends NavItemAdmin { key: number; open: boolean }
const REGIONS: { id: Region; label: string; hint: string }[] = [
  { id: 'top', label: '顶栏', hint: '桌面和平板顶部的胶囊导航。' },
  { id: 'mobile', label: '手机底栏', hint: '手机底部的悬浮导航，最多 5 格；“搜索”“更多”是动作，不是页面。' },
  { id: 'footer', label: '页脚', hint: '页脚里的两列链接（页面类放“浏览”，外链和订阅放“订阅与联系”）。' },
]
const region = ref<Region>('top')
const rows = reactive<Record<Region, Row[]>>({ top: [], mobile: [], footer: [] })
const original = reactive<Record<Region, string>>({ top: '', mobile: '', footer: '' })
const customized = reactive<Record<Region, boolean>>({ top: false, mobile: false, footer: false })
const maxMobile = ref(5)
const pages = ref<AdminPage[]>([])
const errors = reactive<Record<string, string>>({})
const loading = ref(true)
const footer = reactive<SettingsGroups['footer']>({ icp: '', copyright: '', text: '' })
const footerBusy = ref(false)
let key = 1

const sort = useSortable(() => rows[region.value], (n) => { rows[region.value] = n })
const serial = (r: Row[]): string => JSON.stringify(r.map(({ label, kind, target, sticker, enabled }) => ({ label, kind, target, sticker, enabled })))
const dirty = computed(() => (Object.keys(rows) as Region[]).some((r) => serial(rows[r]) !== original[r]))
useLeaveGuard(() => dirty.value)

const kinds = [{ v: 'route', l: '站内页面' }, { v: 'page', l: '独立页面' }, { v: 'category', l: '分类' }, { v: 'tag', l: '标签' }, { v: 'series', l: '系列' }, { v: 'link', l: '链接' }, { v: 'action', l: '动作' }]
const routes = [{ v: '/', l: '首页' }, { v: '/blog', l: '博客' }, { v: '/moments', l: '动态' }, { v: '/archive', l: '归档' }, { v: '/search', l: '搜索页' }]
const actions = [{ v: 'search', l: '搜索（打开搜索浮层）' }, { v: 'more', l: '更多（打开抽屉）' }, { v: 'top', l: '回到顶部' }]

function load(n: NavAdmin): void {
  maxMobile.value = n.mobile_max
  for (const r of ['top', 'mobile', 'footer'] as Region[]) {
    rows[r] = n[r].items.map((i) => ({ ...i, key: key++, open: false }))
    original[r] = serial(rows[r])
    customized[r] = n[r].customized
  }
}
async function refresh(): Promise<void> {
  loading.value = true
  try {
    const [n] = await Promise.all([api.get<NavAdmin>('/nav'), loadTaxonomy(), loadSettings().then((s) => Object.assign(footer, JSON.parse(JSON.stringify(s.groups.footer)))), api.get<ListPage<AdminPage>>('/pages', { per: 100 }).then((p) => { pages.value = p.items })])
    load(n)
  } catch (e) { toastError(e instanceof AdminError ? e.message : '导航加载失败。') } finally { loading.value = false }
}
onMounted(refresh)

function add(): void { rows[region.value].push({ id: null, region: region.value, label: '新条目', kind: 'route', target: '/', sticker: null, enabled: true, key: key++, open: true }) }
function setKind(r: Row, kind: string): void { r.kind = kind; r.target = kind === 'route' ? '/' : kind === 'action' ? 'search' : kind === 'page' ? (pages.value[0]?.slug ?? '') : kind === 'category' ? (taxo.categories[0]?.slug ?? '') : kind === 'tag' ? (taxo.tags[0]?.slug ?? '') : kind === 'series' ? (taxo.series[0]?.slug ?? '') : '' }
const remove = (i: number): void => { rows[region.value].splice(i, 1) }
const tooMany = computed(() => region.value === 'mobile' && rows.mobile.length > maxMobile.value)

async function save(): Promise<void> {
  const r = region.value
  Object.keys(errors).forEach((k) => delete errors[k])
  try {
    const out = await api.put<{ items: NavItemAdmin[]; customized: boolean }>(`/nav/${r}`, { items: rows[r].map(({ label, kind, target, sticker, enabled }) => ({ label, kind, target, sticker, enabled })) })
    rows[r] = out.items.map((i) => ({ ...i, key: key++, open: false }))
    original[r] = serial(rows[r])
    customized[r] = true
    toast(`${REGIONS.find((x) => x.id === r)?.label}导航已保存。`)
  } catch (e) {
    if (e instanceof AdminError) { Object.assign(errors, e.fields); toastError(e.firstField ? `${e.message}（${e.firstField}）` : e.message) } else toastError('保存没有成功。')
  }
}
async function reset(): Promise<void> {
  const r = region.value
  if (!(await confirm({ title: '恢复默认导航？', text: `${REGIONS.find((x) => x.id === r)?.label}会回到出厂的条目，你改过的会丢掉。`, confirm: '恢复默认', danger: true }))) return
  try { const out = await api.post<{ items: NavItemAdmin[] }>(`/nav/${r}/reset`); rows[r] = out.items.map((i) => ({ ...i, key: key++, open: false })); original[r] = serial(rows[r]); customized[r] = false; toast('已恢复默认。') } catch (e) { toastError(e instanceof AdminError ? e.message : '没有成功。') }
}
async function saveFooter(): Promise<void> {
  footerBusy.value = true
  try { await saveGroup('footer', { ...footer }); toast('页脚信息已保存。') } catch (e) { toastError(e instanceof AdminError ? (e.firstField ? `${e.message}（${e.firstField}）` : e.message) : '保存没有成功。') } finally { footerBusy.value = false }
}
/* the picture on the right: the public header, bottom bar and footer drawn with the unsaved items */
const home = ref<HomePayload['blocks'] | null>(null)
const pane = ref<'edit' | 'view'>('edit')
const tabs = [{ value: 'edit' as const, label: '编辑' }, { value: 'view' as const, label: '预览' }]
const slugOf = (list: { slug: string; id: number }[], target: string): string => list.find((x) => x.slug === target)?.slug ?? target
function shown(r: Row): NavItem {
  const external = r.kind === 'link' && /^(https?:|mailto:)/.test(r.target)
  const url = r.kind === 'route' || (r.kind === 'link' && !external) ? r.target
    : r.kind === 'page' ? `/${slugOf(pages.value, r.target)}`
      : r.kind === 'category' ? `/category/${r.target}` : r.kind === 'tag' ? `/tag/${r.target}` : r.kind === 'series' ? `/series/${r.target}` : r.kind === 'link' ? r.target : ''
  return { id: r.id, label: r.label, kind: r.kind as NavItem['kind'], url, action: r.kind === 'action' ? (r.target as NavItem['action']) : null, sticker: r.sticker, external }
}
const previewSite = computed<SiteInfo | null>(() => {
  if (loading.value || !publicSite.value.name) return null
  const region = (r: Region): NavItem[] => rows[r].filter((x) => x.enabled).map(shown)
  return { ...publicSite.value, nav: { top: region('top'), mobile: region('mobile'), footer: region('footer') }, footer: { icp: footer.icp, copyright: footer.copyright || publicSite.value.footer.copyright, text: footer.text } }
})
onMounted(async () => { try { home.value = (await getJSON<HomePayload>('/api/home')).blocks } catch { home.value = [] } })

const targetLabel = (r: Row): string => (r.kind === 'route' ? (routes.find((x) => x.v === r.target)?.l ?? r.target) : r.kind === 'action' ? (actions.find((x) => x.v === r.target)?.l ?? r.target) : r.target)
void settingsState
</script>

<template>
  <div>
    <PageHead title="导航与页脚" sub="顶栏、手机底栏、页脚各有一个条目列表。拖动或在把手上按 ↑ ↓ 调整顺序。">
      <button class="btn btn--fill" type="button" :disabled="!dirty" @click="save"><AIcon name="a-save" />保存{{ REGIONS.find((r) => r.id === region)?.label }}</button>
    </PageHead>
    <p v-if="loading" class="adm-boot" role="status">正在加载导航……</p>
    <div v-else class="adm-homecfg" :data-pane="pane">
      <Segmented v-model="pane" class="adm-homecfg__tabs" label="编辑或预览" :options="tabs" />
      <div class="adm-homecfg__pane">
    <div class="adm-tabs" role="tablist" aria-label="导航区域">
        <button v-for="r in REGIONS" :key="r.id" class="tab" type="button" role="tab" :aria-selected="region === r.id" @click="region = r.id">{{ r.label }}<span class="n">{{ rows[r.id].length }}</span></button>
      </div>
      <p class="adm-hint adm-navhint">{{ REGIONS.find((r) => r.id === region)?.hint }}<template v-if="!customized[region]"> 现在显示的是默认条目，保存后才会变成你的。</template></p>
      <p v-if="tooMany" class="adm-error" role="alert">手机底栏最多 {{ maxMobile }} 格，现在有 {{ rows.mobile.length }} 格，请删掉 {{ rows.mobile.length - maxMobile }} 个再保存。</p>
      <p v-if="errors.items" class="adm-error" role="alert">{{ errors.items }}</p>
  
      <ul class="adm-sortlist">
        <li v-for="(r, i) in rows[region]" :key="r.key" class="adm-card adm-navrow" :class="{ 'is-dragging': sort.dragging.value === i, 'is-off': !r.enabled }" data-sort-row>
          <div class="adm-navrow__head">
            <button class="adm-grip" type="button" :aria-label="`拖动调整「${r.label}」的位置`" v-bind="sort.handle(i)"><AIcon name="a-grip" /></button>
            <span class="adm-sortrow__ico"><AIcon :name="r.sticker || (r.kind === 'action' ? 'sparkle' : 'link')" /></span>
            <span class="adm-sortrow__main"><b>{{ r.label }}</b><small>{{ kinds.find((k) => k.v === r.kind)?.l }} · {{ targetLabel(r) || '（还没填目标）' }}</small></span>
            <label class="switch"><input v-model="r.enabled" type="checkbox" role="switch" :aria-label="`显示「${r.label}」`"><span class="switch__track" aria-hidden="true" /></label>
            <button class="btn btn--sm btn--ghost" type="button" :aria-expanded="r.open" @click="r.open = !r.open"><AIcon name="a-edit" />{{ r.open ? '收起' : '编辑' }}</button>
            <button class="icon-btn icon-btn--ghost" type="button" :aria-label="`删除「${r.label}」`" @click="remove(i)"><AIcon name="a-trash" /></button>
          </div>
          <div v-if="r.open" class="adm-navrow__edit adm-form adm-form--2">
            <Field v-slot="{ id }" label="名称" :error="errors[`items.${i}.label`]"><input :id="id" v-model="r.label" class="input" maxlength="40"></Field>
            <Field v-slot="{ id }" label="类型"><select :id="id" :value="r.kind" class="select" @change="setKind(r, ($event.target as HTMLSelectElement).value)"><option v-for="k in kinds.filter((x) => region !== 'footer' || x.v !== 'action')" :key="k.v" :value="k.v">{{ k.l }}</option></select></Field>
            <Field v-slot="{ id }" label="目标" class="span-2" :error="errors[`items.${i}.target`]">
              <select v-if="r.kind === 'route'" :id="id" v-model="r.target" class="select"><option v-for="x in routes" :key="x.v" :value="x.v">{{ x.l }}（{{ x.v }}）</option></select>
              <select v-else-if="r.kind === 'action'" :id="id" v-model="r.target" class="select"><option v-for="x in actions" :key="x.v" :value="x.v">{{ x.l }}</option></select>
              <select v-else-if="r.kind === 'page'" :id="id" v-model="r.target" class="select"><option v-for="x in pages" :key="x.id" :value="x.slug">{{ x.title }}（/{{ x.slug }}）</option></select>
              <select v-else-if="r.kind === 'category'" :id="id" v-model="r.target" class="select"><option v-for="x in taxo.categories" :key="x.id" :value="x.slug">{{ x.name }}</option></select>
              <select v-else-if="r.kind === 'tag'" :id="id" v-model="r.target" class="select"><option v-for="x in taxo.tags" :key="x.id" :value="x.slug">{{ x.name }}</option></select>
              <select v-else-if="r.kind === 'series'" :id="id" v-model="r.target" class="select"><option v-for="x in taxo.series" :key="x.id" :value="x.slug">{{ x.title }}</option></select>
              <input v-else :id="id" v-model="r.target" class="input" placeholder="https://…、/路径 或 mailto:…" spellcheck="false">
            </Field>
            <Field label="贴纸图标" class="span-2" :error="errors[`items.${i}.sticker`]"><IconPicker v-model="r.sticker" label="贴纸图标" /></Field>
          </div>
        </li>
      </ul>
      <p class="sr-only" role="status" aria-live="polite">{{ sort.announce.value }}</p>
      <div class="adm-navactions">
        <button class="btn btn--sm" type="button" :disabled="loading || (region === 'mobile' && rows.mobile.length >= maxMobile)" @click="add"><AIcon name="a-plus" />加一个条目</button>
        <button class="btn btn--sm btn--ghost" type="button" :disabled="!customized[region]" @click="reset">恢复默认</button>
      </div>
  
      <form class="adm-card adm-section adm-footerform" @submit.prevent="saveFooter">
        <h2>页脚信息</h2>
        <div class="adm-form adm-form--2">
          <Field v-slot="{ id }" label="备案号（可选）" hint="例如：京ICP备…号，会显示在页脚底部并链到工信部网站"><input :id="id" v-model="footer.icp" class="input" maxlength="60"></Field>
          <Field v-slot="{ id }" label="版权文字（可选）" hint="留空显示“© 年份 作者 · 英文站名”"><input :id="id" v-model="footer.copyright" class="input" maxlength="120"></Field>
          <Field v-slot="{ id }" label="页脚简介" class="span-2" hint="站名和一句话下面的第二行"><input :id="id" v-model="footer.text" class="input" maxlength="200"></Field>
        </div>
        <div class="adm-section__foot"><button class="btn btn--fill" type="submit" :disabled="footerBusy"><AIcon name="a-save" />保存页脚信息</button></div>
      </form>
  
      </div>
      <section class="adm-homecfg__preview" aria-label="预览">
        <PreviewFrame :site="previewSite" :home="home" />
      </section>
    </div>
  </div>
</template>
