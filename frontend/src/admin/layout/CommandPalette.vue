<script setup lang="ts">
/* ⌘K / Ctrl+K: jump to any page of the admin, start something new, or find a post, moment or page by its words. */
import { computed, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import type { AdminMoment, AdminPage, AdminPostCard, ListPage } from '../types'
import AIcon from '../ui/AIcon'
import { debounced } from '../use'
import { ALL_ENTRIES } from '../nav'
import { closePalette, paletteOpen } from './palette'

interface Row { key: string; group: string; icon: string; title: string; small: string; to: string }
const router = useRouter()
const dlg = ref<HTMLDialogElement | null>(null)
const input = ref<HTMLInputElement | null>(null)
const q = ref('')
const found = ref<Row[]>([])
const sel = ref(0)
let seq = 0

const CREATE: Row[] = [
  { key: 'new-post', group: '新建', icon: 'a-plus', title: '写一篇文章', small: '打开编辑器', to: '/posts/new' },
  { key: 'new-moment', group: '新建', icon: 'a-plus', title: '发一条动态', small: '动态页顶部的发布框', to: '/moments?compose=1' },
  { key: 'new-page', group: '新建', icon: 'a-plus', title: '新建页面', small: '关于、友链这样的独立页面', to: '/pages/new' },
  { key: 'upload', group: '新建', icon: 'a-upload', title: '上传图片', small: '去媒体库', to: '/media?upload=1' },
]

const rows = computed<Row[]>(() => {
  const term = q.value.trim().toLowerCase()
  const nav: Row[] = ALL_ENTRIES.filter((e) => !term || `${e.label} ${e.keywords ?? ''}`.toLowerCase().includes(term))
    .map((e) => ({ key: `nav${e.to}`, group: '去哪里', icon: e.icon, title: e.label, small: e.to === '/' ? '/admin' : `/admin${e.to}`, to: e.to }))
  const create = CREATE.filter((c) => !term || `${c.title} ${c.small}`.toLowerCase().includes(term))
  // typing a page's name should take you to that page first; words that only appear inside content come after the shortcuts
  return (term ? [...nav, ...create, ...found.value] : [...create, ...nav]).slice(0, 14)
})
const groups = computed(() => {
  const out: { name: string; rows: (Row & { i: number })[] }[] = []
  rows.value.forEach((r, i) => {
    let g = out.find((x) => x.name === r.group)
    if (!g) { g = { name: r.group, rows: [] }; out.push(g) }
    g.rows.push({ ...r, i })
  })
  return out
})

const search = debounced(async () => {
  const term = q.value.trim()
  const mine = ++seq
  if (term.length < 1) { found.value = []; return }
  try {
    const [p, m, g] = await Promise.all([
      api.get<ListPage<AdminPostCard>>('/posts', { q: term, per: 5 }),
      api.get<ListPage<AdminMoment>>('/moments', { q: term, per: 3 }),
      api.get<ListPage<AdminPage>>('/pages', { per: 50 }),
    ])
    if (mine !== seq) return
    found.value = [
      ...p.items.map((x) => ({ key: `p${x.id}`, group: '文章', icon: 'book', title: x.title || '（无标题）', small: x.status === 'published' ? '已发布' : x.status, to: `/posts/${x.id}` })),
      ...m.items.map((x) => ({ key: `m${x.id}`, group: '动态', icon: 'chat', title: (x.text || '（图片）').slice(0, 40), small: '动态', to: `/moments?edit=${x.id}` })),
      ...g.items.filter((x) => `${x.title} ${x.slug}`.toLowerCase().includes(term.toLowerCase())).slice(0, 3).map((x) => ({ key: `g${x.id}`, group: '页面', icon: 'smile', title: x.title, small: `/${x.slug}`, to: `/pages/${x.id}` })),
    ]
    sel.value = 0
  } catch { found.value = [] }
}, 200)

function go(row: Row | undefined): void {
  if (!row) return
  closePalette()
  void router.push(row.to)
}
function onKey(e: KeyboardEvent): void {
  const n = rows.value.length
  if (e.key === 'ArrowDown') { e.preventDefault(); sel.value = (sel.value + 1) % Math.max(n, 1) }
  else if (e.key === 'ArrowUp') { e.preventDefault(); sel.value = (sel.value - 1 + n) % Math.max(n, 1) }
  else if (e.key === 'Enter') { e.preventDefault(); go(rows.value[sel.value]) }
  else if (e.key === 'Escape') { e.preventDefault(); closePalette() }
}

watch(paletteOpen, async (open) => {
  const d = dlg.value
  if (!d) return
  if (open && !d.open) { q.value = ''; found.value = []; sel.value = 0; d.showModal(); await nextTick(); input.value?.focus() }
  else if (!open && d.open) d.close()
})
function onClose(): void { if (!dlg.value?.open) closePalette() }
</script>

<template>
  <dialog ref="dlg" class="dialog dialog--search adm-palette" aria-label="命令面板" @close="onClose" @click.self="closePalette">
    <div class="searchbox">
      <div class="searchbox__top">
        <AIcon name="search" />
        <input ref="input" v-model="q" class="input" type="search" placeholder="跳到某一页、找文章、新建内容……" aria-label="命令面板" autocomplete="off" role="combobox" aria-controls="adm-palette-list" :aria-expanded="rows.length > 0" :aria-activedescendant="rows[sel] ? `pal-${rows[sel]?.key}` : undefined" @input="sel = 0; search()" @keydown="onKey">
        <kbd>Esc</kbd>
      </div>
      <div id="adm-palette-list" class="searchbox__list" role="listbox" aria-label="结果">
        <template v-for="g in groups" :key="g.name">
          <div class="searchbox__group" role="presentation">{{ g.name }}</div>
          <a v-for="r in g.rows" :id="`pal-${r.key}`" :key="r.key" class="searchbox__item" :href="`/admin${r.to === '/' ? '' : r.to}`" role="option" :aria-selected="r.i === sel" @click.prevent="go(r)" @mousemove="sel = r.i">
            <span class="ico"><AIcon :name="r.icon" /></span>
            <span><strong>{{ r.title }}</strong><small>{{ r.small }}</small></span>
          </a>
        </template>
        <p v-if="!rows.length" class="searchbox__status">没有找到「{{ q }}」。</p>
      </div>
      <div class="searchbox__foot"><span>↑ ↓ 选择　↵ 打开</span><span>⌘K / Ctrl K 随时呼出</span></div>
    </div>
  </dialog>
</template>
