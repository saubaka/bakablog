<script setup lang="ts">
/* /blog and the category, tag and series pages: one list with the same controls, so moving between them never rebuilds the page. */
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter, type RouteLocationRaw } from 'vue-router'
import { vFx } from '@/fx/directive'
import FxText from '@/fx/FxText.vue'
import Icon from '@/ui/components/Icon'
import NavLink from '@/ui/components/NavLink.vue'
import { planGrid } from '../cards'
import EmptyState from '../components/EmptyState.vue'
import Pager from '../components/Pager.vue'
import PostCardView from '../components/PostCardView.vue'
import PostRow from '../components/PostRow.vue'
import { site, type PageState } from '../state'
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
const tags = computed(() => [...(props.state.taxonomy?.tags ?? [])].filter((t) => t.count > 0).sort((a, b) => b.count - a.count).slice(0, 12))

/* ---- view: cards or rows (the visitor's choice is remembered; a series is always a numbered list) ---- */
const stored = (() => { try { return localStorage.getItem('bb:view') } catch { return null } })()
const view = ref<'grid' | 'list'>(stored === 'list' ? 'list' : 'grid')
const asList = computed(() => view.value === 'list' || !!series.value)
function pickView(v: 'grid' | 'list'): void {
  view.value = v
  try { localStorage.setItem('bb:view', v) } catch { /* optional */ }
}

const filtered = computed(() => !!(query.value.q || scoped.value))
const { cols } = useViewport()
const plan = computed(() => planGrid(data.value.items, filtered.value ? 'grid' : 'mixed', cols.value))

/* ---- controls ---- */
const qInput = ref(query.value.q)
watch(() => query.value.q, (v) => { qInput.value = v })
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
function sortBy(e: Event): void {
  const v = (e.target as HTMLSelectElement).value
  void router.push({ path: route.path, query: { q: query.value.q || undefined, sort: v === 'new' ? undefined : v } })
}
const pageTo = (n: number): RouteLocationRaw => ({ path: route.path, query: { ...route.query, page: n > 1 ? String(n) : undefined } })
</script>

<template>
  <div class="wrap" :class="{ 'is-list': asList, 'is-filtered': filtered }">
    <header class="page-head">
      <span class="kicker" v-fx="{ type: 'pop', intro: 0 }"><Icon :name="head.icon" />{{ head.kicker }}</span>
      <FxText tag="h1" :text="head.title" :intro="1" />
      <p v-if="head.text" v-fx="{ type: 'fade', intro: 2 }">{{ head.text }}</p>
      <p v-if="series" class="series-status" v-fx="{ type: 'fade', intro: 3 }">
        <span class="tag tag--rose">{{ series.status === 'finished' ? '已完结' : '连载中' }} · {{ data.total }} 篇</span>
      </p>
    </header>

    <div class="filters" v-fx="'fade'">
      <nav class="tabs" aria-label="分类">
        <NavLink class="tab" to="/blog" :current="!scoped">全部<span class="n">{{ total }}</span></NavLink>
        <NavLink v-for="c in categories" :key="c.id" class="tab" :to="c.url" :current="category?.slug === c.slug">{{ c.name }}<span class="n">{{ c.count }}</span></NavLink>
      </nav>
      <div class="filters__bar">
        <form class="searchfield" role="search" @submit.prevent="search(true)">
          <Icon name="search" />
          <input v-model="qInput" class="input" type="search" name="q" placeholder="在博客里搜一搜……" aria-label="搜索文章" autocomplete="off" enterkeyhint="search" :disabled="!!series" @input="search(false)">
        </form>
        <select class="select" aria-label="排序" :value="query.sort" :disabled="!!series" @change="sortBy">
          <option value="new">最新优先</option>
          <option value="old">最早优先</option>
          <option v-if="site.features.stats" value="views">最多阅读</option>
        </select>
        <div class="viewtoggle" role="group" aria-label="显示方式">
          <button type="button" :aria-pressed="!asList" aria-label="卡片" :disabled="!!series" @click="pickView('grid')"><Icon name="grid" /></button>
          <button type="button" :aria-pressed="asList" aria-label="列表" :disabled="!!series" @click="pickView('list')"><Icon name="rows" /></button>
        </div>
      </div>
      <div v-if="tags.length" class="filters__tags">
        <span class="label">标签</span>
        <NavLink v-for="t in tags" :key="t.id" class="tag" :to="tag?.slug === t.slug ? '/blog' : t.url" :current="tag?.slug === t.slug">{{ t.name }}</NavLink>
      </div>
      <div class="result-line">
        <span role="status">共 {{ data.total }} 篇</span>
        <a v-if="site.features.rss" class="text-link" href="/feed/posts.xml"><Icon name="rss" />订阅文章</a>
      </div>
    </div>

    <section class="list-section">
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
    </section>

    <Pager class="list-pager" :page="data.page" :pages="data.pages" :to="pageTo" />
  </div>
</template>
