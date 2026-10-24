<script setup lang="ts">
import { computed, ref } from 'vue'
import { api, AdminError } from '../api/client'
import { ago } from '../format'
import { STATUS_LABEL } from '../labels'
import type { AdminPage, ListPage } from '../types'
import AIcon from '../ui/AIcon'
import { confirm } from '../ui/confirm'
import EmptyBox from '../ui/EmptyBox.vue'
import Menu from '../ui/Menu.vue'
import TableWrap from '../ui/TableWrap.vue'
import PageHead from '../ui/PageHead.vue'
import { toast, toastError } from '../ui/toast'
import { useLoader } from '../use'

const trashed = ref(false)
const { data, loading, error, reload } = useLoader((signal) => api.get<ListPage<AdminPage> & { counts: { trashed: number } }>('/pages', { trashed: trashed.value, per: 100 }, signal), () => trashed.value)
const templateLabel: Record<string, string> = { plain: '纯文', wide: '宽幅', sidebar: '带目录' }
const items = computed(() => data.value?.items ?? [])

async function act(fn: () => Promise<unknown>, done: string): Promise<void> { try { await fn(); toast(done); await reload() } catch (e) { toastError(e instanceof AdminError ? e.message : '没有成功。') } }
async function trash(p: AdminPage): Promise<void> {
  if (await confirm({ title: '移入回收站？', text: `「${p.title}」会从前台消失（也会从导航里去掉），30 天内可以恢复。`, confirm: '移入回收站', danger: true })) await act(() => api.del(`/pages/${p.id}`), '已移入回收站。')
}
const restore = (p: AdminPage) => act(() => api.post(`/pages/${p.id}/restore`), '已恢复。')
async function purge(p: AdminPage): Promise<void> {
  if (await confirm({ title: '永久删除？', text: `「${p.title}」会被彻底删除，不能再恢复。`, confirm: '永久删除', danger: true })) await act(() => api.del(`/pages/${p.id}/purge`), '已永久删除。')
}
</script>

<template>
  <div>
    <PageHead title="页面" sub="关于、友链这样不属于时间线的独立页面。">
      <RouterLink class="btn btn--fill" to="/pages/new"><AIcon name="a-plus" />新建页面</RouterLink>
    </PageHead>
    <div class="adm-tabs" role="tablist" aria-label="页面范围">
      <button class="tab" type="button" role="tab" :aria-selected="!trashed" @click="trashed = false">全部</button>
      <button class="tab" type="button" role="tab" :aria-selected="trashed" @click="trashed = true">回收站<span v-if="data?.counts" class="n">{{ data.counts.trashed }}</span></button>
    </div>
    <p v-if="error" class="adm-error" role="alert">{{ error.message }} <button class="text-link" type="button" @click="reload">重试</button></p>
    <EmptyBox v-else-if="!loading && !items.length" :title="trashed ? '回收站是空的' : '还没有页面'" :text="trashed ? '' : '“关于”页面通常是第一个。'" />
    <TableWrap v-else-if="items.length" label="页面列表">
      <table class="adm-table">
        <thead><tr><th>标题</th><th>地址</th><th>模板</th><th>状态</th><th>出现在</th><th class="is-nowrap">修改</th><th class="is-shrink"><span class="sr-only">操作</span></th></tr></thead>
        <tbody>
          <tr v-for="p in items" :key="p.id">
            <td><RouterLink :to="`/pages/${p.id}`"><b>{{ p.title }}</b></RouterLink></td>
            <td class="adm-mono">/{{ p.slug }}</td>
            <td>{{ templateLabel[p.template] ?? p.template }}</td>
            <td><span class="adm-badge" :class="p.status === 'published' ? 'adm-badge--ok' : ''">{{ STATUS_LABEL[p.status] ?? p.status }}</span></td>
            <td><span v-if="p.in_nav" class="tag tag--sky">顶栏</span><span v-if="p.in_footer" class="tag tag--sky">页脚</span><span v-if="!p.in_nav && !p.in_footer" class="adm-hint">—</span></td>
            <td class="is-nowrap">{{ ago(p.updated_at) }}</td>
            <td>
              <Menu :label="`「${p.title}」的操作`" icon="more" icon-only>
                <template v-if="!p.deleted_at">
                  <RouterLink role="menuitem" :to="`/pages/${p.id}`"><AIcon name="a-edit" />编辑</RouterLink>
                  <a role="menuitem" :href="p.url" target="_blank" rel="noopener"><AIcon name="external" />在前台打开</a>
                  <button role="menuitem" type="button" @click="trash(p)"><AIcon name="a-trash" />移入回收站</button>
                </template>
                <template v-else>
                  <button role="menuitem" type="button" @click="restore(p)"><AIcon name="a-undo" />恢复</button>
                  <button role="menuitem" type="button" @click="purge(p)"><AIcon name="a-trash" />永久删除</button>
                </template>
              </Menu>
            </td>
          </tr>
        </tbody>
      </table>
    </TableWrap>
  </div>
</template>
