<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api } from '../api/client'
import { ago, when } from '../format'
import { actionLabel, TARGET_LABEL } from '../labels'
import type { AuditRow, ListPage, LoginRecord } from '../types'
import EmptyBox from '../ui/EmptyBox.vue'
import TableWrap from '../ui/TableWrap.vue'
import PageHead from '../ui/PageHead.vue'
import Pagination from '../ui/Pagination.vue'
import { useLoader, useRouteQuery } from '../use'

const { state, set } = useRouteQuery({ tab: 'audit', action: '', target: '', page: '1' })
const groups = [{ v: '', l: '全部' }, { v: 'auth.', l: '登录与账号' }, { v: 'post.', l: '文章' }, { v: 'moment.', l: '动态' }, { v: 'page.', l: '页面' }, { v: 'media.', l: '图片' }, { v: 'settings.', l: '设置' }, { v: 'system.', l: '系统' }]
const { data, loading, error, reload } = useLoader((signal) => (state.value.tab === 'audit'
  ? api.get<ListPage<AuditRow>>('/audit', { action: state.value.action, target_type: state.value.target, page: Number(state.value.page), per: 40 }, signal)
  : Promise.resolve(null)), () => state.value)
const { data: logins } = useLoader((signal) => api.get<{ items: LoginRecord[] }>('/auth/logins', undefined, signal))
const REASON: Record<string, string> = { ok: '成功', bad_credentials: '用户名或密码不对', bad_code: '动态码不对', totp_required: '需要二次验证', locked: '被暂时锁定', recovery: '用了恢复码' }
const tabs = [{ id: 'audit', label: '操作日志' }, { id: 'logins', label: '登录记录' }]
const open = ref<number | null>(null)
watch(() => state.value, () => { open.value = null })

/* {"device": "浏览器"} -> 浏览器 ; {"a": 1, "b": "x"} -> a: 1 · b: x */
const KEY: Record<string, string> = { title: '标题', slug: '别名', name: '名称', username: '用户名', device: '设备', bytes: '大小', visibility: '可见性', status: '状态', count: '数量', reason: '原因', safety_backup: '恢复前备份' }
function brief(s: Record<string, unknown>): string {
  const parts = Object.entries(s).map(([k, v]) => `${KEY[k] ?? k}：${typeof v === 'object' ? JSON.stringify(v) : String(v)}`)
  return parts.join(' · ')
}
const targets = computed(() => Object.entries(TARGET_LABEL))
</script>

<template>
  <div>
    <PageHead title="日志" sub="后台里发生过的事：谁、什么时候、做了什么，只增不改；以及每一次登录尝试。" />
    <div class="adm-tabs" role="tablist" aria-label="日志种类">
      <button v-for="t in tabs" :key="t.id" class="tab" type="button" role="tab" :aria-selected="state.tab === t.id" @click="set({ tab: t.id })">{{ t.label }}</button>
    </div>
    <div v-if="state.tab === 'logins'" class="adm-card adm-section">
      <TableWrap label="登录记录">
        <table class="adm-table">
          <thead><tr><th class="is-nowrap">时间</th><th>结果</th><th>网段</th><th>浏览器</th></tr></thead>
          <tbody>
            <tr v-for="(l, i) in logins?.items ?? []" :key="i">
              <td class="is-nowrap" :title="when(l.at)">{{ ago(l.at) }}</td>
              <td><span class="adm-badge" :class="l.success ? 'adm-badge--ok' : 'adm-badge--rose'">{{ REASON[l.reason] ?? l.reason }}</span></td>
              <td class="adm-mono">{{ l.ip_prefix || '—' }}</td><td class="adm-clip">{{ l.user_agent || '—' }}</td>
            </tr>
            <tr v-if="logins && !logins.items.length"><td colspan="4" class="adm-hint">还没有记录。</td></tr>
          </tbody>
        </table>
      </TableWrap>
    </div>
    <div v-if="state.tab === 'audit'" class="adm-toolbar" role="group" aria-label="筛选">
      <select class="select" :value="state.action" aria-label="类型" @change="set({ action: ($event.target as HTMLSelectElement).value })"><option v-for="g in groups" :key="g.v" :value="g.v">{{ g.l }}</option></select>
      <select class="select" :value="state.target" aria-label="对象" @change="set({ target: ($event.target as HTMLSelectElement).value })"><option value="">所有对象</option><option v-for="[k, l] in targets" :key="k" :value="k">{{ l }}</option></select>
      <span class="adm-toolbar__grow" />
      <small v-if="data" class="adm-hint">共 {{ data.total }} 条</small>
    </div>
    <p v-if="state.tab === 'audit' && error" class="adm-error" role="alert">{{ error.message }} <button class="text-link" type="button" @click="reload">重试</button></p>
    <div v-else-if="state.tab === 'audit' && loading && !data" class="adm-skel-grid" aria-busy="true"><span v-for="n in 3" :key="n" class="skel adm-skel" /></div>
    <EmptyBox v-else-if="state.tab === 'audit' && data && !data.items.length" title="没有符合条件的记录" />
    <div v-else-if="state.tab === 'audit' && data" class="adm-card adm-section">
      <TableWrap label="操作日志">
        <table class="adm-table">
          <thead><tr><th class="is-nowrap">时间</th><th>谁</th><th>做了什么</th><th>对象</th><th>网段</th></tr></thead>
          <tbody>
            <tr v-for="a in data.items" :key="a.id">
              <td class="is-nowrap" :title="when(a.at)">{{ ago(a.at) }}</td>
              <td>{{ a.actor }}</td>
              <td><b>{{ actionLabel(a.action) }}</b><small v-if="Object.keys(a.summary).length" class="adm-logsum">{{ brief(a.summary) }}</small></td>
              <td class="is-nowrap">{{ TARGET_LABEL[a.target_type] ?? a.target_type }}<span v-if="a.target_id" class="adm-mono"> #{{ a.target_id }}</span></td>
              <td class="adm-mono">{{ a.ip_prefix || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </TableWrap>
      <Pagination :page="data.page" :pages="data.pages" @go="(n) => set({ page: String(n) }, { keepPage: true })" />
    </div>
  </div>
</template>
