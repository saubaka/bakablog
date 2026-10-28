<script setup lang="ts">
/* /blog and the category, tag and series pages: one list with the same controls, so moving between them never rebuilds the page. */
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter, type RouteLocationRaw } from 'vue-router'
import { vFx } from '@/fx/directive'
import FxText from '@/fx/FxText.vue'
import Icon from '@/ui/components/Icon'
import NavLink from '@/ui/components/NavLink.vue'
import { planGrid } from '../cards'
import Dropdown from '../components/Dropdown.vue'
import EmptyState from '../components/EmptyState.vue'
import Fold from '../components/Fold.vue'
import Pager from '../components/Pager.vue'
import PostCardView from '../components/PostCardView.vue'
import PostRow from '../components/PostRow.vue'
import SwapPane from '../components/SwapPane.vue'
import { dirOf, type Dir } from '../motion'
import { useSlider } from '../slider'
import { loading, site, type PageState } from '../state'
import { useViewport } from '../viewport'

const props = defineProps<{ state: Extract<PageState, { kind: 'blog' | 'taxonomy' }> }>()
const route = useRoute()
const router = useRouter()

const data = computed(() => props.state.data)
const query = computed(() => props.state.query)
const filters = computed(() => data.value.filters)
const category = computed(() => filters.value.category)
const tag = computed(() => filters.value.tag)
const series = computed(() => filters.value.series)
const scoped = computed(() => props.state.kind === 'taxonomy')

const head = computed(() => {
  if (category.value) return { kicker: '分类', icon: 'folder', title: category.value.name, text: category.value.description || `“${category.value.name}”下的文章。` }
  if (tag.value) return { kicker: '标签', icon: 'tag', title: tag.value.name, text: `带有“${tag.value.name}”标签的文章。` }
  if (series.value) return { kicker: '系列', icon: 'list', title: series.value.title, text: series.value.description }
  return { kicker: '博客', icon: 'book', title: query.value.q ? `搜索：${query.value.q}` : '博客', text: query.value.q ? '' : site.value.description }
})

const categories = computed(() => (props.state.taxonomy?.categories ?? []).filter((c) => c.show_on_shelf && c.count > 0))
const total = computed(() => props.state.taxonomy?.total_posts ?? 0)

/* ---- view: cards or rows (the visitor's choice is remembered; a series is always a numbered list) ---- */
const stored = (() => { try { return localStorage.getItem('bb:view') } catch { return null } })()
const view = ref<'grid' | 'list'>(stored === 'list' ? 'list' : 'grid')
const asList = computed(() => view.value === 'list' || !!series.value)
/** Which way the change of the list reads (see SwapPane): cards -> rows moves to the right, rows -> cards to the left, a later page to the right; a new search or order just fades. */
const swapDir = ref<Dir>('none')
function pickView(v: 'grid' | 'list'): void {
  if (view.value === v) return
  swapDir.value = v === 'list' ? 'next' : 'prev'
  view.value = v
  try { localStorage.setItem('bb:view', v) } catch { /* optional */ }
}
watch(() => props.state.data, (now, before) => { swapDir.value = dirOf(now.page, before.page) })

const filtered = computed(() => !!(query.value.q || scoped.value))
const { cols } = useViewport()
const plan = computed(() => planGrid(data.value.items, filtered.value ? 'grid' : 'mixed', cols.value))
/** Whatever makes the list a different list (a page, a search, an order, a category, cards or rows) replaces it as a whole. */
const listKey = computed(() => [asList.value ? 'rows' : 'cards', category.value?.slug, tag.value?.slug, series.value?.slug, query.value.q, query.value.sort, data.value.page].join('|'))

/* ---- the markers that slide to the current choice ---- */
const tabsEl = ref<HTMLElement | null>(null)
const toggleEl = ref<HTMLElement | null>(null)
useSlider(tabsEl, '.tab[aria-current]', () => `${props.state.kind}|${category.value?.slug ?? ''}`)
useSlider(toggleEl, 'button[aria-pressed="true"]', () => asList.value)

/* ---- controls ---- */
const qInput = ref(query.value.q)
const field = ref<HTMLInputElement | null>(null)
watch(() => query.value.q, (v) => { qInput.value = v })
const sorts = computed(() => [
  { value: 'new', label: '最新优先' },
  { value: 'old', label: '最早优先' },
  ...(site.value.features.stats ? [{ value: 'views', label: '最多阅读' }] : []),
])
let timer = 0
function search(now: boolean): void {
  window.clearTimeout(timer)
  const go = (): void => {
    const q = qInput.value.trim()
    const next: RouteLocationRaw = { path: '/blog', query: { q: q || undefined, sort: query.value.sort === 'new' ? undefined : query.value.sort } }
    if (q === query.value.q && route.path === '/blog') return
    void (now ? router.push(next) : router.replace(next))
  }
  if (now) go()
  else timer = window.setTimeout(go, 380)
}
function clear(): void {
  qInput.value = ''
  search(true)
  field.value?.focus({ preventScroll: true })
}
function sortBy(v: string): void {
  void router.push({ path: route.path, query: { q: query.value.q || undefined, sort: v === 'new' ? undefined : v } })
}
const pageTo = (n: number): RouteLocationRaw => ({ path: route.path, query: { ...route.query, page: n > 1 ? String(n) : undefined } })
</script>

<template>
  <div class="wrap" :class="{ 'is-list': asList, 'is-filtered': filtered }">
    <header class="page-head page-head--fold">
      <span class="kicker" v-fx="{ type: 'pop', intro: 0 }"><Icon :name="head.icon" />{{ head.kicker }}</span>
      <FxText tag="h1" :text="head.title" :intro="1" />
      <Fold :show="!!head.text"><Transition name="tick" mode="out-in"><p :key="head.text" v-fx="{ type: 'fade', intro: 2 }">{{ head.text }}</p></Transition></Fold>
      <p v-if="series" class="series-status" v-fx="{ type: 'fade', intro: 3 }">
        <span class="tag tag--rose">{{ series.status === 'finished' ? '已完结' : '连载中' }} · {{ data.total }} 篇</span>
      </p>
    </header>

    <div class="filters" v-fx="'fade'">
      <nav ref="tabsEl" class="tabs" aria-label="分类">
        <i class="slide slide--tab" aria-hidden="true" />
        <NavLink class="tab" to="/blog" :current="!scoped">全部<span class="n">{{ total }}</span></NavLink>
        <NavLink v-for="c in categories" :key="c.id" class="tab" :to="c.url" :current="category?.slug === c.slug">{{ c.name }}<span class="n">{{ c.count }}</span></NavLink>
      </nav>
      <div class="filters__bar">
        <form class="searchfield searchfield--live" :class="{ 'is-busy': loading }" role="search" @submit.prevent="search(true)">
          <Icon name="search" />
          <input ref="field" v-model="qInput" class="input" type="search" name="q" placeholder="在博客里搜一搜……" aria-label="搜索文章" autocomplete="off" enterkeyhint="search" :disabled="!!series" @input="search(false)">
          <Transition name="pop">
            <button v-if="qInput && !series" class="searchfield__clear" type="button" aria-label="清除搜索词" @click="clear"><Icon name="close" /></button>
          </Transition>
          <span class="searchfield__busy" aria-hidden="true" />
        </form>
        <Dropdown class="filters__sort" :model-value="query.sort" :options="sorts" label="排序" :disabled="!!series" @update:model-value="sortBy" />
        <div ref="toggleEl" class="viewtoggle" role="group" aria-label="显示方式">
          <i class="slide slide--thumb" aria-hidden="true" />
          <button type="button" :aria-pressed="!asList" aria-label="卡片" :disabled="!!series" @click="pickView('grid')"><Icon name="grid" /></button>
          <button type="button" :aria-pressed="asList" aria-label="列表" :disabled="!!series" @click="pickView('list')"><Icon name="rows" /></button>
        </div>
      </div>
      <div class="result-line">
        <Transition name="tick" mode="out-in"><span :key="data.total" role="status">共 {{ data.total }} 篇</span></Transition>
      </div>
    </div>

    <section class="list-section">
      <SwapPane :k="listKey" :dir="swapDir">
        <template v-if="data.items.length">
          <div v-if="asList" class="stack">
            <PostRow v-for="p in data.items" :key="p.id" v-fx="'fade'" :post="p" :level="2" />
          </div>
          <div v-else class="grid-6" data-fx-stagger>
            <PostCardView v-for="(p, i) in data.items" :key="p.id" v-fx="'rise'" :class="`span-${plan[i]?.span ?? 3}`" :post="p" :layout="plan[i]?.layout ?? 'cover'" :level="2" :eager="i < 2" />
          </div>
        </template>
        <EmptyState v-else title="这里什么也没有" :text="query.q ? `没有找到和「${query.q}」有关的文章，换个词试试？` : '换个分类或者标签试试。'">
          <NavLink class="btn btn--sm" to="/blog">看全部文章</NavLink>
        </EmptyState>
      </SwapPane>
    </section>

    <Pager class="list-pager" :page="data.page" :pages="data.pages" :to="pageTo" />
  </div>
</template>
