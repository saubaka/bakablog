<script setup lang="ts">
/* The search overlay: opened by the menu's search button, "/" or Ctrl/⌘ K. Results come from /api/search while typing.
   It opens and closes with a short motion (the panel rises in and the veil fades; closing runs the same backwards before the <dialog> really closes), and its rows
   come and go one by one: they fold open with a small stagger, fold shut when a new search no longer has them, and the rows below slide meanwhile. */
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { isAbort } from '@/shared/api'
import Icon from '@/ui/components/Icon'
import type { PostCard, SearchResult } from '@/shared/types'
import { fetchLatest, fetchSearch } from '../data'
import { motionOn } from '../motion'
import { closeSearch, searchOpen } from '../ui'

interface Row { key: string; group: string; icon: string; title: string; small: string; smallHtml: boolean; url: string }
type Entry =
  | { kind: 'group'; key: string; name: string; at: number }
  | { kind: 'row'; key: string; row: Row & { i: number }; at: number }

const CLOSE_MS = 190      // how long the closing motion runs (the CSS in ui/css/pages.css has the same number)

const router = useRouter()
const dlg = ref<HTMLDialogElement | null>(null)
const input = ref<HTMLInputElement | null>(null)
const q = ref('')
const result = ref<SearchResult | null>(null)
const latest = ref<PostCard[]>([])
const busy = ref(false)
const failed = ref(false)
const sel = ref(0)
const recent = ref<string[]>(readRecent())
const shown = ref(false)        // the panel is in its open state (false while it is arriving and while it is leaving)
const alive = ref(false)        // the list exists: made when the overlay opens, so its rows play their entrance every time, dropped once it has closed
let timer = 0
let closeTimer = 0
let ctl: AbortController | null = null

function readRecent(): string[] {
  try { return (JSON.parse(localStorage.getItem('bb:recent') || '[]') as unknown[]).filter((x): x is string => typeof x === 'string').slice(0, 5) } catch { return [] }
}
function remember(term: string): void {
  const t = term.trim()
  if (t.length < 2) return
  recent.value = [t, ...recent.value.filter((x) => x !== t)].slice(0, 5)
  try { localStorage.setItem('bb:recent', JSON.stringify(recent.value)) } catch { /* optional */ }
}

const rows = computed<Row[]>(() => {
  const out: Row[] = []
  const r = result.value
  if (q.value.trim() && r) {
    for (const p of r.groups.posts.slice(0, 5)) out.push({ key: `p${p.id}`, group: '文章', icon: 'book', title: p.title, small: p.snippet || p.summary, smallHtml: !!p.snippet, url: p.url })
    for (const m of r.groups.moments.slice(0, 3)) out.push({ key: `m${m.id}`, group: '动态', icon: 'chat', title: (m.text || '（图片）').slice(0, 40), small: m.snippet || '', smallHtml: !!m.snippet, url: m.url })
    for (const g of r.groups.pages.slice(0, 3)) out.push({ key: `g${g.id}`, group: '页面', icon: 'smile', title: g.title, small: g.snippet, smallHtml: true, url: g.url })
  } else if (!q.value.trim()) {
    for (const p of latest.value) out.push({ key: `l${p.id}`, group: '最近的文章', icon: 'book', title: p.title, small: p.summary, smallHtml: false, url: p.url })
  }
  return out
})

const groups = computed(() => {
  const list: { name: string; rows: (Row & { i: number })[] }[] = []
  rows.value.forEach((row, i) => {
    let g = list.find((x) => x.name === row.group)
    if (!g) { g = { name: row.group, rows: [] }; list.push(g) }
    g.rows.push({ ...row, i })
  })
  return list
})

/** The list as one flat run of keyed pieces (group heads and rows), so that each can come and go on its own. `at` counts the pieces for the stagger. */
const entries = computed<Entry[]>(() => {
  const out: Entry[] = []
  for (const g of groups.value) {
    out.push({ kind: 'group', key: `g:${g.name}`, name: g.name, at: out.length })
    for (const row of g.rows) out.push({ kind: 'row', key: row.key, row, at: out.length })
  }
  return out
})
const showRecent = computed(() => !q.value.trim() && recent.value.length > 0)
const showEmpty = computed(() => !!q.value.trim() && !busy.value && !rows.value.length)
const showBusy = computed(() => busy.value && !rows.value.length)

/** Split a title around the search words so the hits can be marked without any HTML. */
function marked(text: string): { t: string; hit: boolean }[] {
  const term = q.value.trim()
  if (!term) return [{ t: text, hit: false }]
  const out: { t: string; hit: boolean }[] = []
  const lower = text.toLowerCase()
  const needle = term.toLowerCase()
  let at = 0
  for (let i = lower.indexOf(needle); i >= 0; i = lower.indexOf(needle, at)) {
    if (i > at) out.push({ t: text.slice(at, i), hit: false })
    out.push({ t: text.slice(i, i + needle.length), hit: true })
    at = i + needle.length
  }
  if (at < text.length) out.push({ t: text.slice(at), hit: false })
  return out
}

function run(): void {
  ctl?.abort()
  const term = q.value.trim()
  if (!term) { result.value = null; busy.value = false; failed.value = false; return }
  ctl = new AbortController()
  busy.value = true
  failed.value = false
  fetchSearch(term, 'all', ctl.signal)
    .then((r) => { result.value = r; sel.value = 0 })
    .catch((err: unknown) => { if (!isAbort(err)) { failed.value = true; result.value = null } })
    .finally(() => { busy.value = false })
}

function onInput(): void {
  window.clearTimeout(timer)
  timer = window.setTimeout(run, 170)
}

function go(url: string): void {
  remember(q.value)
  closeSearch()
  void router.push(url)
}

function submit(): void {
  const row = rows.value[sel.value]
  if (q.value.trim() && !row) { remember(q.value); closeSearch(); void router.push({ path: '/search', query: { q: q.value.trim() } }); return }
  if (row) go(row.url)
}

function move(d: number): void {
  const n = rows.value.length
  if (n) sel.value = (sel.value + d + n) % n
}

function onKey(e: KeyboardEvent): void {
  if (e.key === 'ArrowDown') { e.preventDefault(); move(1) }
  else if (e.key === 'ArrowUp') { e.preventDefault(); move(-1) }
  else if (e.key === 'Enter') { e.preventDefault(); submit() }
  else if (e.key === 'Escape') { e.preventDefault(); closeSearch() }   // a search field would otherwise only clear its text on the first Esc
}

/** The browser reports a close (Esc, programmatic) as a separate task. If the overlay was opened again in the meantime, that late report is stale. */
function onClose(): void {
  if (!dlg.value?.open) closeSearch()
}

function pickRecent(term: string): void {
  q.value = term
  run()
}

watch(searchOpen, async (open) => {
  const d = dlg.value
  if (!d) return
  window.clearTimeout(closeTimer)
  if (open) {
    q.value = ''; result.value = null; sel.value = 0; failed.value = false; busy.value = false
    alive.value = true
    if (!d.open) d.showModal()
    await nextTick()
    input.value?.focus()
    if (motionOn()) requestAnimationFrame(() => requestAnimationFrame(() => { shown.value = searchOpen.value }))   // after the closed look has been drawn, so there is something to move from
    else shown.value = true
    if (!latest.value.length) fetchLatest(4).then((r) => { latest.value = r.items }).catch(() => undefined)
  } else if (d.open) {
    shown.value = false
    ctl?.abort()
    if (!motionOn()) { d.close(); alive.value = false; return }
    closeTimer = window.setTimeout(() => { if (!searchOpen.value) { d.close(); alive.value = false } }, CLOSE_MS)
  }
})

watch(() => router.currentRoute.value.fullPath, () => { if (searchOpen.value) closeSearch() })
watch(sel, async () => { await nextTick(); dlg.value?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: 'nearest' }) })
onBeforeUnmount(() => { window.clearTimeout(timer); window.clearTimeout(closeTimer); ctl?.abort() })
</script>

<template>
  <dialog ref="dlg" class="dialog dialog--search" :class="{ 'is-shown': shown }" aria-label="搜索" @close="onClose" @cancel.prevent="closeSearch" @click="(e) => e.target === dlg && closeSearch()">
    <div class="searchbox">
      <div class="searchbox__top" :class="{ 'is-busy': busy }">
        <Icon name="search" />
        <input ref="input" v-model="q" class="input" type="search" placeholder="搜文章、动态、页面……" aria-label="搜索关键词" autocomplete="off" role="combobox" aria-controls="search-list" aria-autocomplete="list" :aria-expanded="rows.length > 0" :aria-activedescendant="rows[sel] ? `sr-${rows[sel]?.key}` : undefined" enterkeyhint="search" @input="onInput" @keydown="onKey">
        <kbd>Esc</kbd>
        <span class="searchbox__busy" aria-hidden="true" />
      </div>
      <TransitionGroup v-if="alive" id="search-list" tag="div" name="fold" appear class="searchbox__list" role="listbox" aria-label="搜索结果">
        <div v-if="showRecent" key="recent" class="fold" role="presentation" :style="{ '--i': 0 }">
          <div class="fold__in" role="presentation">
            <div class="searchbox__group" role="presentation">最近搜过</div>
            <div class="searchbox__recent"><button v-for="r in recent" :key="r" type="button" class="tag" @click="pickRecent(r)">{{ r }}</button></div>
          </div>
        </div>
        <div v-for="e in entries" :key="e.key" class="fold" role="presentation" :style="{ '--i': Math.min(e.at, 9) }">
          <div class="fold__in" role="presentation">
            <div v-if="e.kind === 'group'" class="searchbox__group" role="presentation">{{ e.name }}</div>
            <a v-else :id="`sr-${e.row.key}`" class="searchbox__item" :href="e.row.url" role="option" :aria-selected="e.row.i === sel" @click.prevent="go(e.row.url)" @mousemove="sel = e.row.i">
              <span class="ico"><Icon :name="e.row.icon" /></span>
              <span>
                <strong><template v-for="(part, k) in marked(e.row.title)" :key="k"><mark v-if="part.hit">{{ part.t }}</mark><template v-else>{{ part.t }}</template></template></strong>
                <small v-if="e.row.small && e.row.smallHtml" v-html="e.row.small" />
                <small v-else-if="e.row.small">{{ e.row.small }}</small>
              </span>
            </a>
          </div>
        </div>
        <div v-if="showEmpty" key="empty" class="fold" role="presentation">
          <div class="fold__in" role="presentation">
            <div class="empty searchbox__empty">
              <strong>{{ failed ? '搜索暂时不可用' : `没有找到「${q.trim()}」` }}</strong>
              <span>{{ failed ? '过一会儿再试试。' : '换个词试试？或者去归档里翻一翻。' }}</span>
            </div>
          </div>
        </div>
        <div v-if="showBusy" key="busy" class="fold" role="presentation">
          <div class="fold__in" role="presentation"><p class="searchbox__status" role="status">正在找……</p></div>
        </div>
      </TransitionGroup>
      <div class="searchbox__foot"><span>↑ ↓ 选择　↵ 打开</span><span>按 / 随时呼出</span></div>
    </div>
  </dialog>
</template>
