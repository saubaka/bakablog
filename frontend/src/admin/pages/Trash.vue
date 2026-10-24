<script setup lang="ts">
import { computed } from 'vue'
import { api, AdminError } from '../api/client'
import { ago } from '../format'
import { TARGET_LABEL } from '../labels'
import type { TrashItem } from '../types'
import AIcon from '../ui/AIcon'
import { confirm } from '../ui/confirm'
import EmptyBox from '../ui/EmptyBox.vue'
import TableWrap from '../ui/TableWrap.vue'
import PageHead from '../ui/PageHead.vue'
import { toast, toastError } from '../ui/toast'
import { useLoader } from '../use'

const { data, loading, error, reload } = useLoader((signal) => api.get<{ items: TrashItem[]; retention_days: number }>('/trash', undefined, signal))
const items = computed(() => data.value?.items ?? [])
async function act(fn: () => Promise<unknown>, done: string): Promise<void> { try { await fn(); toast(done); await reload() } catch (e) { toastError(e instanceof AdminError ? e.message : '没有成功。') } }
const restore = (t: TrashItem) => act(() => api.post('/trash/restore', { type: t.type, id: t.id }), '已恢复。')
async function purge(t: TrashItem): Promise<void> {
  if (await confirm({ title: '永久删除？', text: `「${t.title || '无标题'}」会被彻底删除，不能再恢复。`, confirm: '永久删除', danger: true })) await act(() => api.del(`/trash/${t.type}/${t.id}`), '已永久删除。')
}
async function empty(): Promise<void> {
  if (await confirm({ title: '清空回收站？', text: `这 ${items.value.length} 项会被彻底删除，不能再恢复。`, confirm: '清空', danger: true, typeToConfirm: '清空' })) await act(() => api.del('/trash'), '回收站已清空。')
}
</script>

<template>
  <div>
    <PageHead title="回收站" :sub="`删除的文章、动态、页面和图片先放在这里，${data?.retention_days ?? 30} 天后自动清理。`">
      <button v-if="items.length" class="btn btn--danger" type="button" @click="empty"><AIcon name="a-trash" />清空回收站</button>
    </PageHead>
    <p v-if="error" class="adm-error" role="alert">{{ error.message }} <button class="text-link" type="button" @click="reload">重试</button></p>
    <EmptyBox v-else-if="!loading && !items.length" title="回收站是空的" text="删掉的东西会先来这里，想反悔还来得及。" />
    <TableWrap v-else-if="items.length" label="回收站">
      <table class="adm-table">
        <thead><tr><th>内容</th><th>类型</th><th class="is-nowrap">删除于</th><th class="is-nowrap">剩余</th><th class="is-shrink"><span class="sr-only">操作</span></th></tr></thead>
        <tbody>
          <tr v-for="t in items" :key="`${t.type}${t.id}`">
            <td><b>{{ t.title || '（无标题）' }}</b></td>
            <td><span class="adm-badge">{{ TARGET_LABEL[t.type] ?? t.type }}</span></td>
            <td class="is-nowrap">{{ ago(t.deleted_at) }}</td>
            <td class="is-nowrap">{{ t.days_left }} 天</td>
            <td class="is-nowrap"><button class="btn btn--sm" type="button" @click="restore(t)"><AIcon name="a-undo" />恢复</button><button class="btn btn--sm btn--ghost" type="button" @click="purge(t)"><AIcon name="a-trash" />永久删除</button></td>
          </tr>
        </tbody>
      </table>
    </TableWrap>
  </div>
</template>
