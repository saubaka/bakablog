<script setup lang="ts">
/* /moments: the timeline. Filters (tag, mood, month) are part of the address, so a filtered view can be shared; "load more" follows the cursor. */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { RouteLocationRaw } from 'vue-router'
import { isAbort } from '@/shared/api'
import { monthLabel } from '@/shared/format'
import { vFx } from '@/fx/directive'
import FxText from '@/fx/FxText.vue'
import Icon from '@/ui/components/Icon'
import EmptyState from '../components/EmptyState.vue'
import MomentView from '../components/MomentView.vue'
import { fetchMoments } from '../data'
import { monthOf } from '../fmt'
import type { Moment } from '@/shared/types'
import type { PageState } from '../state'

const props = defineProps<{ state: Extract<PageState, { kind: 'moments' }> }>()

const query = computed(() => props.state.query)
const meta = computed(() => props.state.data.meta)
const filtered = computed(() => !!(query.value.tag || query.value.mood || query.value.month))
const pinned = computed(() => (filtered.value ? [] : props.state.data.pinned ?? []))

/* ---- the loaded part of the timeline (grows with "load more", starts over when the filters change) ---- */
const items = ref<Moment[]>([...props.state.data.items])
const cursor = ref<string | null>(props.state.data.next_cursor)
const busy = ref(false)
const failed = ref(false)
watch(() => props.state.data, (d) => { items.value = [...d.items]; cursor.value = d.next_cursor; failed.value = false })

let ctl: AbortController | null = null
async function more(): Promise<void> {
  if (busy.value || !cursor.value) return
  busy.value = true
  failed.value = false
  ctl = new AbortController()
  try {
    const page = await fetchMoments(query.value, cursor.value, ctl.signal)
    const seen = new Set(items.value.map((m) => m.id))
    items.value = [...items.value, ...page.items.filter((m) => !seen.has(m.id))]
    cursor.value = page.next_cursor
  } catch (err) {
    if (!isAbort(err)) failed.value = true
  } finally {
    busy.value = false
  }
}

/* start loading shortly before the button comes into view */
const sentinel = ref<HTMLElement | null>(null)
let io: IntersectionObserver | null = null
onMounted(() => {
  if (!('IntersectionObserver' in window) || !sentinel.value) return
  io = new IntersectionObserver((entries) => { if (entries.some((e) => e.isIntersecting) && !failed.value) void more() }, { rootMargin: '0px 0px 600px 0px' })
  io.observe(sentinel.value)
})
onBeforeUnmount(() => { io?.disconnect(); ctl?.abort() })

/* ---- grouping by month (in the site's time zone) ---- */
const groups = computed(() => {
  const out: { key: string; label: string; items: Moment[] }[] = []
  for (const m of items.value) {
    const key = monthOf(m.published_at)
    let g = out[out.length - 1]
    if (!g || g.key !== key) { g = { key, label: monthLabel(key), items: [] }; out.push(g) }
    g.items.push(m)
  }
  return out
})

/* ---- filter links ---- */
function to(patch: Partial<Record<'tag' | 'mood' | 'month', string>>): RouteLocationRaw {
  const q = { tag: query.value.tag, mood: query.value.mood, month: query.value.month, ...patch }
  return { path: '/moments', query: { tag: q.tag || undefined, mood: q.mood || undefined, month: q.month || undefined } }
}
const toggle = (key: 'tag' | 'mood', value: string): RouteLocationRaw => to({ [key]: query.value[key] === value ? '' : value })

/* ---- the little calendar of the month being looked at ---- */
const calMonth = computed(() => query.value.month || meta.value?.months[0]?.month || '')
const cal = computed(() => {
  const m = /^(\d{4})-(\d{2})$/.exec(calMonth.value)
  if (!m) return null
  const year = Number(m[1])
  const month = Number(m[2])
  const first = (new Date(Date.UTC(year, month - 1, 1)).getUTCDay() + 6) % 7   // Monday first
  const days = new Date(Date.UTC(year, month, 0)).getUTCDate()
  const has = new Set(meta.value?.days[calMonth.value] ?? [])
  const now = new Date()
  const today = now.getFullYear() === year && now.getMonth() + 1 === month ? now.getDate() : 0
  return { label: `${year} 年 ${month} 月`, blanks: first, days: Array.from({ length: days }, (_, i) => ({ n: i + 1, has: has.has(i + 1), today: i + 1 === today })) }
})
</script>

<template>
  <div class="wrap">
    <header class="page-head">
      <span class="kicker" v-fx="{ type: 'pop', intro: 0 }"><Icon name="chat" />动态</span>
      <FxText tag="h1" text="碎碎念" :intro="1" />
      <p v-fx="{ type: 'fade', intro: 2 }">想到什么发什么：一句话、几张照片、一个链接。</p>
    </header>

    <div class="moments-layout">
      <aside v-if="meta && meta.months.length" class="month-nav" aria-label="按月份浏览">
        <div v-fx="'fade'">
          <h2>月份</h2>
          <ol>
            <li><RouterLink :to="to({ month: '' })" :class="{ 'is-active': !query.month }" :aria-current="!query.month ? 'page' : undefined">全部</RouterLink></li>
            <li v-for="m in meta.months" :key="m.month"><RouterLink :to="to({ month: m.month })" :class="{ 'is-active': query.month === m.month }" :aria-current="query.month === m.month ? 'page' : undefined">{{ monthLabel(m.month) }}<span class="n">{{ m.count }}</span></RouterLink></li>
          </ol>
        </div>
        <div v-if="cal" v-fx="'fade'" class="minical" :aria-label="`${cal.label}的日历`">
          <div class="minical__head"><span>{{ cal.label }}</span></div>
          <div class="minical__grid" aria-hidden="true">
            <span v-for="w in ['一', '二', '三', '四', '五', '六', '日']" :key="w">{{ w }}</span>
            <span v-for="b in cal.blanks" :key="`b${b}`" />
            <span v-for="d in cal.days" :key="d.n" :class="{ has: d.has, today: d.today }">{{ d.n }}</span>
          </div>
        </div>
      </aside>

      <div class="moments-main">
        <nav v-if="meta && meta.months.length" v-fx="'fade'" class="month-chips" aria-label="按月份浏览">
          <RouterLink class="tag" :to="to({ month: '' })" :aria-current="!query.month ? 'page' : undefined">全部</RouterLink>
          <RouterLink v-for="m in meta.months" :key="m.month" class="tag" :to="to({ month: m.month })" :aria-current="query.month === m.month ? 'page' : undefined">{{ monthLabel(m.month) }}</RouterLink>
        </nav>
        <div v-if="meta && (meta.tags.length || meta.moods.length)" class="moment-filters" v-fx="'fade'">
          <RouterLink class="tag" to="/moments" :aria-current="!filtered ? 'true' : undefined">全部</RouterLink>
          <template v-if="meta.tags.length">
            <span class="label">标签</span>
            <RouterLink v-for="t in meta.tags" :key="t.id" class="tag" :to="toggle('tag', t.slug)" :aria-current="query.tag === t.slug ? 'true' : undefined">{{ t.name }}<span class="n">{{ t.count }}</span></RouterLink>
          </template>
          <template v-if="meta.moods.length">
            <span class="label">心情</span>
            <RouterLink v-for="m in meta.moods" :key="m.id" class="tag" :to="toggle('mood', m.id)" :aria-current="query.mood === m.id ? 'true' : undefined">{{ m.label }}<span class="n">{{ m.count }}</span></RouterLink>
          </template>
        </div>

        <div v-if="pinned.length || items.length" class="timeline">
          <div class="timeline__spine" v-fx="'spine'" aria-hidden="true" />
          <MomentView v-for="m in pinned" :key="`pin${m.id}`" :moment="m" pinned />
          <template v-for="g in groups" :key="g.key">
            <div class="month-sep" :id="`m-${g.key}`" v-fx="'fade'"><span><Icon name="calendar" />{{ g.label }}</span></div>
            <MomentView v-for="m in g.items" :key="m.id" :moment="m" />
          </template>
        </div>
        <EmptyState v-else title="这里还没有动态" :text="filtered ? '换个筛选条件试试。' : '等我想到什么就来发。'">
          <RouterLink v-if="filtered" class="btn btn--sm" to="/moments">看全部动态</RouterLink>
        </EmptyState>

        <div ref="sentinel" class="moments-more">
          <button v-if="cursor && !busy" v-fx="'fade'" class="btn" type="button" @click="more"><Icon name="arrow-d" />{{ failed ? '没加载出来，再试一次' : '加载更多' }}</button>
          <p v-else-if="busy" role="status">正在加载……</p>
          <p v-else-if="items.length > 3" class="moments-end">到底啦。</p>
        </div>
      </div>
    </div>
  </div>
</template>
