import { createRouter, createWebHistory, type RouteLocationNormalized, type RouteRecordRaw, type Router, type RouterScrollBehavior } from 'vue-router'
import { beacon } from '@/shared/api'
import type { BootData } from '@/shared/types'
import { isRedirect, loadRoute, type Redirect } from './data'
import { applyHead, headFor } from './head'
import { loading, setPage, site, type PageState } from './state'
import { pageSwapped, setPendingScroll, whenPageReady } from './view'

declare module 'vue-router' {
  interface RouteMeta {
    /** The data this navigation loaded; the page component receives it as a prop. */
    state?: PageState
  }
}

/** Addresses the Flask server answers itself (admin shell, feeds, API ...): never handled by the router, always a real page load. */
const SERVER_PATHS = /^\/(admin|api|media|feed|assets)(\/|$)|^\/(sitemap\.xml|robots\.txt|favicon\.(ico|svg)|manifest\.webmanifest)$/
export const isServerPath = (path: string): boolean => SERVER_PATHS.test(path)

const stub = { render: () => null }
export const routes: RouteRecordRaw[] = [
  { path: '/', name: 'home', component: stub },
  { path: '/blog', name: 'blog', component: stub },
  { path: '/blog/:slug', name: 'post', component: stub },
  { path: '/category/:slug', name: 'category', component: stub },
  { path: '/tag/:slug', name: 'tag', component: stub },
  { path: '/series/:slug', name: 'series', component: stub },
  { path: '/archive', name: 'archive', component: stub },
  { path: '/moments', name: 'moments', component: stub },
  { path: '/moments/:id(\\d+)', name: 'moment', component: stub },
  { path: '/search', name: 'search', component: stub },
  { path: '/:slug([^/]+)', name: 'page', component: stub },
  { path: '/:pathMatch(.*)*', name: 'not-found', component: stub },
]

/** Navigations that only change the filter (search text, sort) keep the scroll position; everything else starts at the top.
    A page change never animates the scroll (`instant`, whatever `html { scroll-behavior: smooth }` says): a smooth scroll-to-top that is still running
    when the visitor presses Back would carry on after the old position was restored and drag the list to the top. Only #fragments glide. */
const scrollBehavior: RouterScrollBehavior = async (to, from, saved) => {
  // (an async function runs synchronously up to its first await, so this is set before the new page is inserted)
  // a swapped page is inserted at its start position (see view.ts); a #fragment is reached from the top by the glide below
  setPendingScroll(pageSwapped() ? { left: saved?.left ?? 0, top: saved?.top ?? 0 } : null)
  if (pageSwapped()) await whenPageReady()
  if (saved) return { ...saved, behavior: 'instant' }
  if (to.hash) return { el: to.hash, top: 96, behavior: 'smooth' }
  if (from.name !== undefined && to.path === from.path && to.query.page === from.query.page) return false
  return { top: 0, behavior: 'instant' }
}

let controller: AbortController | null = null
let appRouter: Router | null = null
/** Pages that were asked for ahead of time (the page-turn gesture asks while the push is under way) and are still fresh. */
const warm = new Map<string, { at: number; result: Promise<PageState | Redirect> }>()
const WARM_MS = 20_000

/** Start fetching what opening `path` will need, so that when the visitor really goes there the answer is already in. Costs one request; failures are ignored here
    (the real navigation asks again). */
export function warmRoute(path: string): void {
  if (!appRouter) return
  const hit = warm.get(path)
  if (hit && Date.now() - hit.at < WARM_MS) return
  const result = loadRoute(appRouter.resolve(path) as unknown as RouteLocationNormalized, new AbortController().signal, null)
  result.catch(() => { warm.delete(path) })
  warm.set(path, { at: Date.now(), result })
}
let loadingTimer = 0
let firstView = true

function startLoading(): void {
  window.clearTimeout(loadingTimer)
  loadingTimer = window.setTimeout(() => { loading.value = true }, 140)
}
function stopLoading(): void {
  window.clearTimeout(loadingTimer)
  loading.value = false
}

function errorState(): PageState {
  return { kind: '500', status: 500, data: { message: site.value.texts.error_text } }
}

/** A short key: pages with the same key are updated in place, pages with different keys are replaced (and cross-faded). */
export function viewKey(route: RouteLocationNormalized): string {
  switch (route.name) {
    case 'blog': case 'category': case 'tag': case 'series': return 'list'
    case 'moments': return 'moments'
    case 'search': return 'search'
    default: return route.path
  }
}

export function createAppRouter(initial: BootData | null): Router {
  const router = createRouter({ history: createWebHistory(), routes, scrollBehavior })
  appRouter = router
  let boot = initial

  router.beforeEach((to) => {
    if (isServerPath(to.path)) {
      window.location.assign(to.fullPath)
      return false
    }
    controller?.abort()
    controller = new AbortController()
    startLoading()
    return true
  })

  router.beforeResolve(async (to, from) => {
    const signal = (controller ??= new AbortController()).signal
    if (from.meta.state && to.path === from.path && JSON.stringify(to.query) === JSON.stringify(from.query)) {
      to.meta.state = from.meta.state     // only the #fragment changed: nothing to load
      return true
    }
    try {
      const first = boot
      boot = null
      const ahead = warm.get(to.fullPath)
      warm.delete(to.fullPath)
      let result: PageState | Redirect | null = null
      if (ahead && !first && Date.now() - ahead.at < WARM_MS) result = await ahead.result.catch(() => null)
      result ??= await loadRoute(to, signal, first)
      if (isRedirect(result)) return { path: result.redirect, replace: true }
      to.meta.state = result
    } catch (err) {
      if (signal.aborted) return false
      console.error(err)
      to.meta.state = errorState()
    }
    return true
  })

  router.afterEach((to, from, failure) => {
    stopLoading()
    if (failure || !to.meta.state) return
    pageSwapped(viewKey(to) !== viewKey(from) && from.name !== undefined)
    setPage(to.meta.state)
    applyHead(headFor(to.meta.state, site.value, to.fullPath))
    // a page view is a new path: a #fragment, a filter or the next page of the same list is not another visit
    if (site.value.features.stats && !import.meta.env.DEV && to.meta.state.kind !== '500' && (from.name === undefined || to.path !== from.path)) {
      beacon(to.path, firstView ? document.referrer : '')
    }
    firstView = false
  })

  router.onError((err) => {
    stopLoading()
    console.error(err)
  })

  return router
}

