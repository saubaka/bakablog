<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { api, AdminError } from '../api/client'
import { ago, bytes, duration, when } from '../format'
import type { SystemStatus } from '../types'
import AIcon from '../ui/AIcon'
import PageHead from '../ui/PageHead.vue'
import { toast, toastError } from '../ui/toast'

interface JobInfo { at?: string; ok?: boolean; result?: unknown }
const status = ref<SystemStatus | null>(null)
const jobs = ref<Record<string, JobInfo>>({})
const running = reactive<Record<string, boolean>>({})
const error = ref('')

const JOBS: { name: string; label: string; text: string }[] = [
  { name: 'reindex', label: '重建搜索索引', text: '搜索结果不对劲、或者直接改过数据库之后用。' },
  { name: 'thumbnails', label: '补生成缩略图', text: '重新生成缺失的图片尺寸。' },
  { name: 'cache', label: '刷新站点缓存', text: '让公开页面立刻重新生成。' },
  { name: 'vacuum', label: '整理数据库', text: '回收空闲空间，可能需要几秒。' },
  { name: 'housekeeping', label: '日常清理', text: '清理过期的登录会话和旧的统计数据。' },
  { name: 'trash', label: '清理回收站', text: '永久删除超过 30 天的内容。' },
]

async function load(): Promise<void> {
  try {
    const [s, j] = await Promise.all([api.get<SystemStatus>('/system/status'), api.get<{ jobs: Record<string, JobInfo> }>('/system/jobs')])
    status.value = s
    jobs.value = j.jobs
  } catch (e) { error.value = e instanceof AdminError ? e.message : '系统状态加载失败。' }
}
onMounted(load)

async function run(name: string): Promise<void> {
  running[name] = true
  try {
    const out = await api.post<{ ok: boolean }>(`/system/jobs/${name}`)
    toast(out.ok ? '已完成。' : '运行失败了，详情看下面的记录。')
    await load()
  } catch (e) { toastError(e instanceof AdminError ? e.message : '没有成功。') } finally { running[name] = false }
}
const brief = (r: unknown): string => {
  if (r === undefined || r === null) return ''
  const s = typeof r === 'string' ? r : JSON.stringify(r)
  return s.length > 140 ? `${s.slice(0, 140)}…` : s
}
const used = computed(() => (status.value ? status.value.disk.total - status.value.disk.free : 0))
const usedPct = computed(() => (status.value && status.value.disk.total ? Math.round((used.value / status.value.disk.total) * 100) : 0))
const schemaOk = computed(() => status.value?.schema_revision === status.value?.schema_head)
</script>

<template>
  <div>
    <PageHead title="系统" sub="版本、占用空间和维护任务。">
      <button class="btn" type="button" @click="load"><AIcon name="a-refresh" />刷新</button>
    </PageHead>
    <p v-if="error" class="adm-error" role="alert">{{ error }}</p>
    <div v-if="status" class="adm-stack">
      <section class="adm-card adm-section" aria-labelledby="st-h">
        <h2 id="st-h">运行状态</h2>
        <dl class="adm-dl">
          <div><dt>版本</dt><dd>{{ status.version }} <small>构建 {{ status.build }} · {{ status.env }}</small></dd></div>
          <div><dt>已运行</dt><dd>{{ duration(status.uptime_seconds) }}</dd></div>
          <div><dt>Python / SQLite</dt><dd>{{ status.python }} / {{ status.sqlite }}</dd></div>
          <div><dt>数据库结构</dt><dd>{{ status.schema_revision }} <span class="adm-badge" :class="schemaOk ? 'adm-badge--ok' : 'adm-badge--rose'">{{ schemaOk ? '最新' : `需要升级到 ${status.schema_head}` }}</span></dd></div>
          <div><dt>站点地址</dt><dd class="adm-mono">{{ status.site_url }}</dd></div>
          <div><dt>缓存版本</dt><dd>{{ status.site_version }}</dd></div>
          <div><dt>搜索索引</dt><dd>{{ status.search_rows }} 条</dd></div>
          <div><dt>最近备份</dt><dd>{{ status.last_backup?.at ? ago(status.last_backup.at) : '还没有' }}<small> · 共 {{ status.backups }} 份</small></dd></div>
        </dl>
      </section>

      <section class="adm-card adm-section" aria-labelledby="sp-h">
        <h2 id="sp-h">占用空间</h2>
        <dl class="adm-dl">
          <div><dt>数据库</dt><dd>{{ bytes(status.db_bytes) }}</dd></div>
          <div><dt>图片</dt><dd>{{ bytes(status.media_bytes) }}</dd></div>
          <div><dt>备份</dt><dd>{{ bytes(status.backup_bytes) }}</dd></div>
          <div><dt>磁盘</dt><dd>剩余 {{ bytes(status.disk.free) }} <small>/ 共 {{ bytes(status.disk.total) }}</small></dd></div>
        </dl>
        <div class="adm-meter" role="img" :aria-label="`磁盘已用 ${usedPct}%`"><i :style="{ width: `${Math.max(1, usedPct)}%` }" /></div>
      </section>

      <section class="adm-card adm-section" aria-labelledby="jb-h">
        <h2 id="jb-h">维护任务</h2>
        <p class="adm-hint">日常任务（每天备份、清理）由系统定时器自动运行；这里可以手动跑一次。</p>
        <ul class="adm-jobs">
          <li v-for="j in JOBS" :key="j.name">
            <div class="adm-jobs__text">
              <b>{{ j.label }}</b><small>{{ j.text }}</small>
              <small v-if="jobs[j.name]" class="adm-jobs__last">上次：{{ when(jobs[j.name]?.at) }} · <span :class="jobs[j.name]?.ok ? 'is-ok' : 'is-bad'">{{ jobs[j.name]?.ok ? '成功' : '失败' }}</span><template v-if="brief(jobs[j.name]?.result)"> · {{ brief(jobs[j.name]?.result) }}</template></small>
              <small v-else class="adm-jobs__last">还没有运行过</small>
            </div>
            <button class="btn btn--sm" type="button" :disabled="running[j.name]" @click="run(j.name)">{{ running[j.name] ? '运行中……' : '现在运行' }}</button>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>
