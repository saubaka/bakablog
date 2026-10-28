<script setup lang="ts">
/* /moments: the timeline. Filters (tag, mood, month) are part of the address, so a filtered view can be shared; "load more" follows the cursor.
   There is no list of tags or moods on the page: a tag is picked on a moment itself, and while a tag or mood filter is on, a chip says so and clears it. */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { RouteLocationRaw } from 'vue-router'
import { isAbort } from '@/shared/api'
import { monthLabel } from '@/shared/format'
import { vFx } from '@/fx/directive'
import FxText from '@/fx/FxText.vue'
import Icon from '@/ui/components/Icon'
import EmptyState from '../components/EmptyState.vue'
import Fold from '../components/Fold.vue'
import MomentView from '../components/MomentView.vue'
import SwapPane from '../components/SwapPane.vue'
import { fetchMoments } from '../data'
import { monthOf } from '../fmt'
import { dirOf, motionOn, type Dir } from '../motion'
import { useSlider } from '../slider'
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

/** The tag / mood filter that is on (it came from a link on a moment), named for the chip that clears it. */
const active = computed(() => {
  const out: { key: string; kind: string; label: string }[] = []
  const q = query.value
  if (q.tag) out.push({ key: 'tag', kind: '标签', label: meta.value?.tags.find((t) => t.slug === q.tag)?.name ?? q.tag })
  if (q.mood) out.push({ key: 'mood', kind: '心情', label: meta.value?.moods.find((m) => m.id === q.mood)?.label ?? q.mood })
  return out
})

/* ---- which way a change of month reads: a newer month comes in from the right, an older one from the left ("all months" counts as the newest) ---- */
const NEWEST = '9999-99'
const dir = ref<Dir>('none')
watch(query, (now, before) => { dir.value = dirOf(now.month || NEWEST, before.month || NEWEST) })
const listKey = computed(() => `${query.value.tag}|${query.value.mood}|${query.value.month}`)

/* ---- the markers and the strip of months follow the month being looked at ---- */
const monthList = ref<HTMLElement | null>(null)
const chips = ref<HTMLElement | null>(null)
useSlider(monthList, 'a.is-active', () => query.value.month)
watch(() => query.value.month, async () => {
  await nextTick()
  const strip = chips.value
  const at = strip?.querySelector<HTMLElement>('[aria-current]')
  if (strip && at) strip.scrollTo({ left: at.offsetLeft - (strip.clientWidth - at.offsetWidth) / 2, behavior: motionOn() ? 'smooth' : 'auto' })
})

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
const calDir = ref<Dir>('none')
watch(calMonth, (now, before) => { calDir.value = dirOf(now, before) })
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
          <ol ref="monthList">
            <i class="slide slide--bar" aria-hidden="true" />
            <li><RouterLink :to="to({ month: '' })" :class="{ 'is-active': !query.month }" :aria-current="!query.month ? 'page' : undefined">全部</RouterLink></li>
            <li v-for="m in meta.months" :key="m.month"><RouterLink :to="to({ month: m.month })" :class="{ 'is-active': query.month === m.month }" :aria-current="query.month === m.month ? 'page' : undefined">{{ monthLabel(m.month) }}<span class="n">{{ m.count }}</span></RouterLink></li>
          </ol>
        </div>
        <div v-if="cal" v-fx="'fade'" class="minical" :aria-label="`${cal.label}的日历`">
          <SwapPane :k="calMonth" :dir="calDir" pane-class="minical__pane">
            <div class="minical__head"><span>{{ cal.label }}</span></div>
            <div class="minical__grid" aria-hidden="true">
              <span v-for="w in ['一', '二', '三', '四', '五', '六', '日']" :key="w">{{ w }}</span>
              <span v-for="b in cal.blanks" :key="`b${b}`" />
              <span v-for="d in cal.days" :key="d.n" :class="{ has: d.has, today: d.today }" :style="{ '--i': d.n }">{{ d.n }}</span>
            </div>
          </SwapPane>
        </div>
      </aside>

      <div class="moments-main">
        <nav v-if="meta && meta.months.length" ref="chips" v-fx="'fade'" class="month-chips" aria-label="按月份浏览">
          <RouterLink class="tag" :to="to({ month: '' })" :aria-current="!query.month ? 'page' : undefined">全部</RouterLink>
          <RouterLink v-for="m in meta.months" :key="m.month" class="tag" :to="to({ month: m.month })" :aria-current="query.month === m.month ? 'page' : undefined">{{ monthLabel(m.month) }}</RouterLink>
        </nav>
        <Fold :show="active.length > 0">
          <div class="moment-now" role="status" v-fx="'fade'">
            <span v-for="f in active" :key="f.key" class="tag tag--rose"><span class="label">{{ f.kind }}</span>{{ f.label }}</span>
            <RouterLink class="text-link" :to="to({ tag: '', mood: '' })">清除筛选</RouterLink>
          </div>
        </Fold>

        <SwapPane :k="listKey" :dir="dir">
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
        </SwapPane>

        <div ref="sentinel" class="moments-more">
          <Transition name="tick" mode="out-in">
            <button v-if="cursor && !busy" key="more" v-fx="'fade'" class="btn" type="button" @click="more"><Icon name="arrow-d" />{{ failed ? '没加载出来，再试一次' : '加载更多' }}</button>
            <p v-else-if="busy" key="busy" role="status">正在加载……</p>
            <p v-else-if="items.length > 3" key="end" class="moments-end">到底啦。</p>
          </Transition>
        </div>
      </div>
    </div>
  </div>
</template>
