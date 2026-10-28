<script setup lang="ts">
/* /search?q=…: the full results page. The overlay (header button, "/") is for quick jumps; this page is for looking through everything. */
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter, type RouteLocationRaw } from 'vue-router'
import { vFx } from '@/fx/directive'
import FxText from '@/fx/FxText.vue'
import Phrase from '@/fx/Phrase'
import Icon from '@/ui/components/Icon'
import NavLink from '@/ui/components/NavLink.vue'
import EmptyState from '../components/EmptyState.vue'
import Fold from '../components/Fold.vue'
import Stamp from '../components/Stamp.vue'
import SwapPane from '../components/SwapPane.vue'
import { when } from '../fmt'
import { dirOf, type Dir } from '../motion'
import { useSlider } from '../slider'
import { loading, type PageState } from '../state'

const props = defineProps<{ state: Extract<PageState, { kind: 'search' }> }>()
const route = useRoute()
const router = useRouter()
const q = ref(props.state.q)
const field = ref<HTMLInputElement | null>(null)
watch(() => props.state.q, (v) => { q.value = v })

/* the result type tabs: a marker slides to the current one; the results come in from the side the tab is on */
const ORDER = ['all', 'post', 'moment', 'page']
const dir = ref<Dir>('none')
watch(() => [props.state.q, props.state.type] as const, ([word, type], [before, was]) => { dir.value = word === before ? dirOf(ORDER.indexOf(type), ORDER.indexOf(was)) : 'none' })
const tabsEl = ref<HTMLElement | null>(null)
useSlider(tabsEl, '.tab[aria-current]', () => `${!!props.state.data}|${props.state.type}`)

const groups = computed(() => props.state.data?.groups ?? { posts: [], moments: [], pages: [] })
const counts = computed(() => ({ post: groups.value.posts.length, moment: groups.value.moments.length, page: groups.value.pages.length }))
const tabs = computed(() => [
  { id: 'all', label: '全部', n: props.state.data?.total ?? 0 },
  { id: 'post', label: '文章', n: counts.value.post },
  { id: 'moment', label: '动态', n: counts.value.moment },
  { id: 'page', label: '页面', n: counts.value.page },
] as const)

function clear(): void {
  q.value = ''
  field.value?.focus({ preventScroll: true })
}

function submit(): void {
  const term = q.value.trim()
  void router.push({ path: '/search', query: { q: term || undefined, type: props.state.type === 'all' ? undefined : props.state.type } })
}
const typeTo = (t: string): RouteLocationRaw => ({ path: route.path, query: { q: props.state.q || undefined, type: t === 'all' ? undefined : t } })
const text = (m: { text: string; snippet?: string }): string => m.text || '（图片）'
</script>

<template>
  <div class="wrap">
    <header class="page-head">
      <span class="kicker" v-fx="{ type: 'pop', intro: 0 }"><Icon name="search" />搜索</span>
      <FxText tag="h1" :text="state.q ? `找「${state.q}」` : '找点什么'" :intro="1" />
    </header>

    <form class="searchfield searchfield--live search-page__field" :class="{ 'is-busy': loading }" role="search" v-fx="'fade'" @submit.prevent="submit">
      <Icon name="search" />
      <input ref="field" v-model="q" class="input" type="search" name="q" placeholder="搜文章、动态、页面……" aria-label="搜索关键词" autocomplete="off" enterkeyhint="search">
      <Transition name="pop">
        <button v-if="q" class="searchfield__clear" type="button" aria-label="清除搜索词" @click="clear"><Icon name="close" /></button>
      </Transition>
      <span class="searchfield__busy" aria-hidden="true" />
    </form>

    <Fold :show="!!state.data">
      <nav ref="tabsEl" class="tabs search-page__tabs" v-fx="'fade'" aria-label="结果类型">
        <i class="slide slide--tab" aria-hidden="true" />
        <RouterLink v-for="t in tabs" :key="t.id" class="tab" :to="typeTo(t.id)" :aria-current="state.type === t.id ? 'page' : undefined">{{ t.label }}<span class="n">{{ t.n }}</span></RouterLink>
      </nav>
    </Fold>

    <SwapPane :k="`${state.q}|${state.type}`" :dir="dir">
      <template v-if="state.data">
        <div v-if="state.data.total" class="search-page__results">
          <section v-if="groups.posts.length" aria-label="文章">
            <h2 class="search-page__group" v-fx="'fade'">文章</h2>
            <div class="stack">
              <NavLink v-for="p in groups.posts" :key="p.id" v-fx="'fade'" class="postrow" :to="p.url">
                <Stamp :iso="p.published_at" small />
                <div>
                  <h3 class="postrow__title"><Phrase :text="p.title" /></h3>
                  <p v-if="p.snippet" class="postrow__sum" v-html="p.snippet" />
                  <p v-else class="postrow__sum">{{ p.summary }}</p>
                </div>
                <Icon name="arrow-r" class="postrow__go" />
              </NavLink>
            </div>
          </section>
          <section v-if="groups.moments.length" aria-label="动态">
            <h2 class="search-page__group" v-fx="'fade'">动态</h2>
            <div class="stack">
              <NavLink v-for="m in groups.moments" :key="m.id" v-fx="'fade'" class="postrow" :to="m.url">
                <div class="stamp stamp--sm" aria-hidden="true"><Icon name="chat" /></div>
                <div>
                  <h3 v-if="m.snippet" class="postrow__title" v-html="m.snippet" />
                  <h3 v-else class="postrow__title">{{ text(m).slice(0, 60) }}</h3>
                  <p class="postrow__sum">{{ when(m.published_at) }}</p>
                </div>
                <Icon name="arrow-r" class="postrow__go" />
              </NavLink>
            </div>
          </section>
          <section v-if="groups.pages.length" aria-label="页面">
            <h2 class="search-page__group" v-fx="'fade'">页面</h2>
            <div class="stack">
              <NavLink v-for="g in groups.pages" :key="g.id" v-fx="'fade'" class="postrow" :to="g.url">
                <div class="stamp stamp--sm" aria-hidden="true"><Icon name="smile" /></div>
                <div>
                  <h3 class="postrow__title"><Phrase :text="g.title" /></h3>
                  <p v-if="g.snippet" class="postrow__sum" v-html="g.snippet" />
                </div>
                <Icon name="arrow-r" class="postrow__go" />
              </NavLink>
            </div>
          </section>
        </div>
        <EmptyState v-else :title="`没有找到「${state.q}」`" text="换个词试试？或者去归档里翻一翻。">
          <NavLink class="btn btn--sm" to="/archive">去归档</NavLink>
        </EmptyState>
      </template>
      <div v-else class="empty search-page__hint">
        <strong>想找什么？</strong>
        <span>文章、动态和页面都能搜，中文不用分词。</span>
      </div>
    </SwapPane>
  </div>
</template>
