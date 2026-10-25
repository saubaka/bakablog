<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterView, useRouter } from 'vue-router'
import Lightbox from './components/Lightbox.vue'
import Sprite from '@/ui/components/Sprite.vue'
import ProgressTag from './layout/ProgressTag.vue'
import SearchDialog from './layout/SearchDialog.vue'
import SiteFooter from './layout/SiteFooter.vue'
import TabBar from './layout/TabBar.vue'
import ThreadNav from './layout/ThreadNav.vue'
import { viewKey } from './router'
import { startPull, turning } from './pull'
import { loading, page, site, type PageState } from './state'
import { openSearch } from './ui'
import { applyPendingScroll, focusPageTitle, notifyPageReady, pageSwapped } from './view'
import type { Component } from 'vue'
import type { RouteLocationNormalizedLoaded } from 'vue-router'
import Archive from './pages/Archive.vue'
import ErrorPage from './pages/ErrorPage.vue'
import Home from './pages/Home.vue'
import MomentPage from './pages/MomentPage.vue'
import Moments from './pages/Moments.vue'
import NotFound from './pages/NotFound.vue'
import PageView from './pages/PageView.vue'
import Post from './pages/Post.vue'
import PostList from './pages/PostList.vue'
import Search from './pages/Search.vue'

const views: Record<PageState['kind'], Component> = {
  home: Home, blog: PostList, taxonomy: PostList, post: Post, archive: Archive, moments: Moments, moment: MomentPage,
  page: PageView, search: Search, '404': NotFound, '500': ErrorPage,
}
const viewFor = (r: RouteLocationNormalizedLoaded): Component | null => (r.meta.state ? views[r.meta.state.kind] : null)

const router = useRouter()
const stage = ref<HTMLElement | null>(null)
let stopPull: (() => void) | null = null
const announce = ref('')
watch(page, () => { window.setTimeout(() => { announce.value = document.title }, 60) })

/* the new page is in the document: start it at the top (or where Back left it) before the motion engine places its elements */
function onEnter(): void {
  applyPendingScroll()
}

function onEntered(): void {
  const swapped = pageSwapped()
  notifyPageReady()
  if (swapped) focusPageTitle()
}

function skip(): void {
  document.getElementById('main')?.focus({ preventScroll: false })
}

/* "/" and Ctrl/⌘ K open the search overlay unless the visitor is typing somewhere */
function onKey(e: KeyboardEvent): void {
  const el = document.activeElement as HTMLElement | null
  const typing = !!el && (/^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName) || el.isContentEditable)
  if ((e.key === '/' && !typing && !e.metaKey && !e.ctrlKey && !e.altKey) || ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k')) {
    e.preventDefault()
    openSearch()
  }
}
onMounted(() => {
  document.addEventListener('keydown', onKey)
  if (stage.value) stopPull = startPull(stage.value, router)       // scrolling past the edge of a page turns to the next / previous entry of the menu
})
onBeforeUnmount(() => { document.removeEventListener('keydown', onKey); stopPull?.() })
</script>

<template>
  <Sprite />
  <a class="skip-link" href="#main" @click.prevent="skip">跳到正文</a>
  <div class="topline" :class="{ 'is-on': loading }" aria-hidden="true" />
  <ThreadNav :items="site.nav.top" variant="side" label="主导航" />
  <div ref="stage" class="page-stage">
    <main id="main" tabindex="-1">
      <RouterView v-slot="{ route }">
        <!-- while a page is turned by scrolling past its edge the old page is already out of sight: the swap needs no cross-fade of its own ("page-turn" has no styles, so it
             ends on the next frame) and the page itself does the moving -->
        <Transition :name="turning ? 'page-turn' : 'page'" mode="out-in" @enter="onEnter" @after-enter="onEntered">
          <component :is="viewFor(route)" v-if="route.meta.state" :key="viewKey(route)" :state="route.meta.state" />
        </Transition>
      </RouterView>
    </main>
    <SiteFooter />
  </div>
  <TabBar />
  <ProgressTag />
  <SearchDialog />
  <Lightbox />
  <div class="sr-only" role="status" aria-live="polite">{{ announce }}</div>
</template>
