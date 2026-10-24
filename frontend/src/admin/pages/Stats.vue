<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, AdminError } from '../api/client'
import { loadSettings, saveGroup } from '../settings'
import type { StatsResponse } from '../types'
import EmptyBox from '../ui/EmptyBox.vue'
import TableWrap from '../ui/TableWrap.vue'
import PageHead from '../ui/PageHead.vue'
import Segmented from '../ui/Segmented.vue'
import SwitchField from '../ui/SwitchField.vue'
import { toast, toastError } from '../ui/toast'
import { useLoader } from '../use'

const days = ref<7 | 30 | 90>(30)
const { data, loading, error, reload } = useLoader((signal) => api.get<StatsResponse>('/stats', { days: days.value }, signal), days)
const enabled = ref(true)
const ready = ref(false)
onMounted(async () => { try { enabled.value = (await loadSettings()).groups.stats.enabled; ready.value = true } catch { ready.value = true } })
async function toggle(): Promise<void> {
  try { await saveGroup('stats', { enabled: enabled.value }); toast(enabled.value ? '已开始统计访问。' : '已停止统计，之前的数据还在。') } catch (e) { enabled.value = !enabled.value; toastError(e instanceof AdminError ? e.message : '没有成功。') }
}

const options = [{ value: 7 as const, label: '7 天' }, { value: 30 as const, label: '30 天' }, { value: 90 as const, label: '90 天' }]
const peak = computed(() => Math.max(1, ...(data.value?.series.map((d) => d.views) ?? [0])))
const bars = computed(() => {
  const s = data.value?.series ?? []
  const n = s.length || 1
  const gap = 2
  const w = (600 - gap * (n - 1)) / n
  return s.map((d, i) => ({ ...d, x: i * (w + gap), w, h: d.views ? Math.max(3, (d.views / peak.value) * 150) : 1.5 }))
})
const topMax = computed(() => Math.max(1, ...(data.value?.top_posts.map((p) => p.views) ?? [0])))
const refMax = computed(() => Math.max(1, ...(data.value?.referrers.map((r) => r.count) ?? [0])))
const DEVICE: Record<string, string> = { phone: '手机', tablet: '平板', desktop: '电脑', unknown: '其他' }
const devices = computed(() => {
  const d = data.value?.devices ?? {}
  const total = Object.values(d).reduce((a, b) => a + b, 0) || 1
  return Object.entries(d).sort((a, b) => b[1] - a[1]).map(([k, n]) => ({ key: k, label: DEVICE[k] ?? k, n, pct: Math.round((n / total) * 100) }))
})
const empty = computed(() => !!data.value && data.value.total_views === 0)
const short = (day: string): string => day.slice(5).replace('-', '/')
const summary = computed(() => (data.value ? `最近 ${data.value.days} 天，每天的访问次数，最高 ${peak.value} 次` : ''))
</script>

<template>
  <div>
    <PageHead title="访问统计" sub="只数页面被打开的次数，不记录个人信息，不用 cookie；访客用每天变化的哈希估算。">
      <Segmented v-model="days" label="统计范围" :options="options" />
    </PageHead>
    <div v-if="ready" class="adm-card adm-statswitch">
      <SwitchField v-model="enabled" label="记录访问统计" hint="关闭后不再记录新的访问，已有数据保留；公开页面也不再发送统计请求。" @update:model-value="toggle" />
    </div>
    <p v-if="error" class="adm-error" role="alert">{{ error.message }} <button class="text-link" type="button" @click="reload">重试</button></p>
    <div v-else-if="loading && !data" class="adm-skel-grid" aria-busy="true"><span v-for="n in 3" :key="n" class="skel adm-skel" /></div>

    <template v-if="data">
      <section class="adm-stats adm-stats--3" aria-label="汇总">
        <div class="adm-card adm-stat"><small>访问次数</small><b>{{ data.total_views }}</b><span>最近 {{ data.days }} 天</span></div>
        <div class="adm-card adm-stat"><small>估算访客</small><b>{{ data.total_uniques }}</b><span>每天按哈希去重后相加</span></div>
        <div class="adm-card adm-stat"><small>日均访问</small><b>{{ (data.total_views / data.days).toFixed(1) }}</b><span>每天</span></div>
      </section>

      <EmptyBox v-if="empty" title="这段时间还没有访问记录" :text="enabled ? '有人打开页面之后，这里就会出现数字。' : '统计现在是关闭的，打开上面的开关后才会开始记录。'" />
      <template v-else>
        <section class="adm-card adm-chart" aria-labelledby="chart-h">
          <h2 id="chart-h">每天的访问</h2>
          <svg class="adm-chart__svg" viewBox="0 0 600 160" preserveAspectRatio="none" role="img" :aria-label="summary">
            <line x1="0" y1="159" x2="600" y2="159" stroke="var(--line)" stroke-width="1" vector-effect="non-scaling-stroke" />
            <rect v-for="b in bars" :key="b.day" :x="b.x" :y="159 - b.h" :width="b.w" :height="b.h" rx="1.5" fill="var(--sky-300)"><title>{{ b.day }}：{{ b.views }} 次访问，约 {{ b.uniques }} 位访客</title></rect>
          </svg>
          <div class="adm-chart__axis"><span>{{ short(data.series[0]?.day ?? '') }}</span><span>最高 {{ peak }} 次</span><span>{{ short(data.series[data.series.length - 1]?.day ?? '') }}</span></div>
          <details class="adm-chart__table">
            <summary>用表格查看</summary>
            <TableWrap label="每日访问">
              <table class="adm-table"><thead><tr><th>日期</th><th class="is-num">访问</th><th class="is-num">访客</th></tr></thead>
                <tbody><tr v-for="d in [...data.series].reverse()" :key="d.day"><td>{{ d.day }}</td><td class="is-num">{{ d.views }}</td><td class="is-num">{{ d.uniques }}</td></tr></tbody></table>
            </TableWrap>
          </details>
        </section>

        <div class="adm-two">
          <section class="adm-card" aria-labelledby="top-h">
            <h2 id="top-h">热门文章</h2>
            <ol v-if="data.top_posts.length" class="adm-rank">
              <li v-for="p in data.top_posts" :key="p.id ?? p.title">
                <span class="adm-rank__t"><a v-if="p.url" :href="p.url" target="_blank" rel="noopener">{{ p.title }}</a><template v-else>{{ p.title }}</template></span>
                <span class="adm-rank__n">{{ p.views }}</span>
                <span class="adm-rank__bar" aria-hidden="true"><i :style="{ width: `${(p.views / topMax) * 100}%` }" /></span>
              </li>
            </ol>
            <EmptyBox v-else title="还没有文章被读过" />
          </section>
          <section class="adm-card" aria-labelledby="ref-h">
            <h2 id="ref-h">从哪里来</h2>
            <ol v-if="data.referrers.length" class="adm-rank">
              <li v-for="r in data.referrers" :key="r.domain">
                <span class="adm-rank__t">{{ r.domain }}</span><span class="adm-rank__n">{{ r.count }}</span>
                <span class="adm-rank__bar" aria-hidden="true"><i :style="{ width: `${(r.count / refMax) * 100}%` }" /></span>
              </li>
            </ol>
            <EmptyBox v-else title="没有外部来源" text="直接输入网址、书签、订阅阅读器都不算来源。" />
            <h2 class="adm-chart__sub">设备</h2>
            <ul v-if="devices.length" class="adm-devices">
              <li v-for="d in devices" :key="d.key"><span>{{ d.label }}</span><b>{{ d.pct }}%</b><small>{{ d.n }} 次</small></li>
            </ul>
          </section>
        </div>
      </template>
    </template>
  </div>
</template>
