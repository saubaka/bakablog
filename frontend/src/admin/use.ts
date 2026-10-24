import { onBeforeUnmount, onMounted, ref, shallowRef, watch, type Ref, type WatchSource } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { AdminError } from './api/client'
import { confirm } from './ui/confirm'

/** Load something when the page opens and whenever `source` changes; a newer request cancels the older one, so a slow answer never overwrites a fast one. */
export function useLoader<T>(fetcher: (signal: AbortSignal) => Promise<T>, source?: WatchSource | WatchSource[]): {
  data: Ref<T | null>; loading: Ref<boolean>; error: Ref<AdminError | null>; reload: () => Promise<void>
} {
  const data = shallowRef<T | null>(null) as Ref<T | null>
  const loading = ref(true)
  const error = ref<AdminError | null>(null)
  let ctl: AbortController | null = null
  async function reload(): Promise<void> {
    ctl?.abort()
    const mine = (ctl = new AbortController())
    loading.value = true
    error.value = null
    try {
      const result = await fetcher(mine.signal)
      if (mine === ctl) data.value = result
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') return
      if (mine === ctl) error.value = e instanceof AdminError ? e : new AdminError(0, 'unknown', String(e))
    } finally {
      if (mine === ctl) loading.value = false
    }
  }
  onMounted(reload)
  if (source) watch(source, reload)
  onBeforeUnmount(() => ctl?.abort())
  return { data, loading, error, reload }
}

export function debounced<A extends unknown[]>(fn: (...args: A) => void, ms: number): ((...args: A) => void) & { cancel: () => void } {
  let t = 0
  const run = ((...args: A) => { window.clearTimeout(t); t = window.setTimeout(() => fn(...args), ms) }) as ((...args: A) => void) & { cancel: () => void }
  run.cancel = () => window.clearTimeout(t)
  return run
}

/** Ask before leaving a page with unsaved work: a route change gets a dialog, closing the tab gets the browser's own prompt. */
export function useLeaveGuard(dirty: () => boolean, message = '有改动还没有保存，离开会丢掉它们。', guardUpdates = false): void {
  const beforeUnload = (e: BeforeUnloadEvent): void => { if (dirty()) { e.preventDefault(); e.returnValue = '' } }
  onMounted(() => window.addEventListener('beforeunload', beforeUnload))
  onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))
  const guard = async (): Promise<boolean> => {
    if (!dirty()) return true
    return confirm({ title: '离开这一页？', text: message, confirm: '离开', cancel: '留下', danger: true })
  }
  onBeforeRouteLeave(guard)
  if (guardUpdates) onBeforeRouteUpdate((to, from) => to.path === from.path || guard())
}

/** Wrap a save: one flag for "saving", errors become field messages (422) or a thrown AdminError for the caller to show. */
export function useSubmit(): { busy: Ref<boolean>; fields: Ref<Record<string, string>>; run: <T>(fn: () => Promise<T>) => Promise<T | undefined> } {
  const busy = ref(false)
  const fields = ref<Record<string, string>>({})
  async function run<T>(fn: () => Promise<T>): Promise<T | undefined> {
    if (busy.value) return undefined
    busy.value = true
    fields.value = {}
    try {
      return await fn()
    } catch (e) {
      if (e instanceof AdminError && e.status === 422) { fields.value = e.fields; throw e }
      throw e
    } finally {
      busy.value = false
    }
  }
  return { busy, fields, run }
}

import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

/** Filters that live in the address (?status=draft&page=2): a filtered list can be bookmarked, and Back brings the same list again. */
export function useRouteQuery<T extends Record<string, string>>(defaults: T) {
  const route = useRoute()
  const router = useRouter()
  const state = computed(() => {
    const out: Record<string, string> = { ...defaults }
    for (const k of Object.keys(defaults)) {
      const v = route.query[k]
      const first = Array.isArray(v) ? v[0] : v
      if (typeof first === 'string') out[k] = first
    }
    return out as T
  })
  function set(patch: Partial<T>, opts: { keepPage?: boolean } = {}): void {
    const next: Record<string, string> = { ...state.value, ...(patch as Record<string, string>) }
    if (!opts.keepPage && !('page' in patch)) next.page = '1'
    const query: Record<string, string> = {}
    for (const [k, v] of Object.entries(next)) if (v !== '' && v !== defaults[k]) query[k] = v
    void router.replace({ path: route.path, query })
  }
  return { state, set }
}
