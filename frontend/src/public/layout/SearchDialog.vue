<script setup lang="ts">
/* The search overlay: opened by the header button, the bar's search button, "/" or Ctrl/⌘ K. Results come from /api/search while typing. */
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { isAbort } from '@/shared/api'
import Icon from '@/ui/components/Icon'
import type { PostCard, SearchResult } from '@/shared/types'
import { fetchLatest, fetchSearch } from '../data'
import { closeSearch, searchOpen } from '../ui'

interface Row { key: string; group: string; icon: string; title: string; small: string; smallHtml: boolean; url: string }

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
let timer = 0
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
  if (open && !d.open) {
    q.value = ''; result.value = null; sel.value = 0; failed.value = false
    d.showModal()
    await nextTick()
    input.value?.focus()
    if (!latest.value.length) fetchLatest(4).then((r) => { latest.value = r.items }).catch(() => undefined)
  } else if (!open && d.open) {
    d.close()
  }
})

watch(() => router.currentRoute.value.fullPath, () => { if (searchOpen.value) closeSearch() })
watch(sel, async () => { await nextTick(); dlg.value?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: 'nearest' }) })
onBeforeUnmount(() => { window.clearTimeout(timer); ctl?.abort() })
</script>

<template>
  <dialog ref="dlg" class="dialog dialog--search" aria-label="搜索" @close="onClose" @click="(e) => e.target === dlg && closeSearch()">
    <div class="searchbox">
      <div class="searchbox__top">
        <Icon name="search" />
        <input ref="input" v-model="q" class="input" type="search" placeholder="搜文章、动态、页面……" aria-label="搜索关键词" autocomplete="off" role="combobox" aria-controls="search-list" aria-autocomplete="list" :aria-expanded="rows.length > 0" :aria-activedescendant="rows[sel] ? `sr-${rows[sel]?.key}` : undefined" enterkeyhint="search" @input="onInput" @keydown="onKey">
        <kbd>Esc</kbd>
      </div>
      <div id="search-list" class="searchbox__list" role="listbox" aria-label="搜索结果">
        <template v-if="!q.trim() && recent.length">
          <div class="searchbox__group" role="presentation">最近搜过</div>
          <div class="searchbox__recent"><button v-for="r in recent" :key="r" type="button" class="tag" @click="pickRecent(r)">{{ r }}</button></div>
        </template>
        <template v-for="g in groups" :key="g.name">
          <div class="searchbox__group" role="presentation">{{ g.name }}</div>
          <a v-for="row in g.rows" :id="`sr-${row.key}`" :key="row.key" class="searchbox__item" :href="row.url" role="option" :aria-selected="row.i === sel" @click.prevent="go(row.url)" @mousemove="sel = row.i">
            <span class="ico"><Icon :name="row.icon" /></span>
            <span>
              <strong><template v-for="(part, k) in marked(row.title)" :key="k"><mark v-if="part.hit">{{ part.t }}</mark><template v-else>{{ part.t }}</template></template></strong>
              <small v-if="row.small && row.smallHtml" v-html="row.small" />
              <small v-else-if="row.small">{{ row.small }}</small>
            </span>
          </a>
        </template>
        <div v-if="q.trim() && !busy && !rows.length" class="empty searchbox__empty">
          <strong>{{ failed ? '搜索暂时不可用' : `没有找到「${q.trim()}」` }}</strong>
          <span>{{ failed ? '过一会儿再试试。' : '换个词试试？或者去归档里翻一翻。' }}</span>
        </div>
        <p v-if="busy && !rows.length" class="searchbox__status" role="status">正在找……</p>
      </div>
      <div class="searchbox__foot"><span>↑ ↓ 选择　↵ 打开</span><span>按 / 随时呼出</span></div>
    </div>
  </dialog>
</template>
