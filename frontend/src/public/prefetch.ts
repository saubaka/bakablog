/* Getting the neighbouring pages of the menu ready before they are asked for, so that going there (a click on a bead, a push past the edge of the page) never has to wait for
   the network: when a page has arrived and the browser has nothing else to do, the data of the entries next to it is fetched (then the rest of the menu, a little later). Each
   costs one or two small requests and is kept for a minute (router.ts `warmRoute`). Not done on a "save data" connection or in a hidden tab. */
import type { Router } from 'vue-router'
import { currentIndex } from './nav'
import { activeMenu } from './menu'
import { isWarm, warmRoute } from './router'

const SETTLE_MS = 700        // after a page has arrived: let its own entrance (and the images) go first
const GAP_MS = 220           // between two requests

const idle = (fn: () => void, timeout = 1500): void => {
  if (typeof requestIdleCallback === 'function') requestIdleCallback(fn, { timeout })
  else window.setTimeout(fn, 60)
}

function allowed(): boolean {
  if (document.visibilityState !== 'visible') return false
  const c = (navigator as Navigator & { connection?: { saveData?: boolean; effectiveType?: string } }).connection
  return !(c?.saveData || c?.effectiveType === '2g' || c?.effectiveType === 'slow-2g')
}

/** The entries to get ready, the nearest first: the next one, the previous one, then the others by distance. */
export function prefetchOrder(urls: string[], here: number): string[] {
  if (here < 0) return urls
  return urls.map((url, i) => ({ url, i })).filter(({ i }) => i !== here).sort((a, b) => Math.abs(a.i - here) - Math.abs(b.i - here) || b.i - a.i).map(({ url }) => url)
}

export function startPrefetch(router: Router): () => void {
  let timer = 0
  let run = 0

  const go = (token: number): void => {
    if (!allowed()) return
    const items = activeMenu().filter((it) => it.kind !== 'action' && !it.external && it.url.startsWith('/'))
    const path = router.currentRoute.value.path
    const order = prefetchOrder(items.map((it) => it.url), currentIndex(items, path)).filter((url) => url !== path && !isWarm(url))
    order.forEach((url, n) => window.setTimeout(() => { if (token === run && allowed()) idle(() => { void warmRoute(url) }) }, n * GAP_MS))
  }
  const schedule = (): void => {
    window.clearTimeout(timer)
    const token = ++run
    timer = window.setTimeout(() => idle(() => go(token)), SETTLE_MS)
  }

  const stopHook = router.afterEach((_to, _from, failure) => { if (!failure) schedule() })
  document.addEventListener('visibilitychange', schedule)
  schedule()
  return () => { stopHook(); document.removeEventListener('visibilitychange', schedule); window.clearTimeout(timer); run += 1 }
}
