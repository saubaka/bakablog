<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { api, AdminError, download } from '../api/client'
import { ago, bytes, when } from '../format'
import { loadSettings, saveGroup } from '../settings'
import type { BackupRow, SettingsGroups } from '../types'
import AIcon from '../ui/AIcon'
import { confirm } from '../ui/confirm'
import EmptyBox from '../ui/EmptyBox.vue'
import Field from '../ui/Field.vue'
import TableWrap from '../ui/TableWrap.vue'
import PageHead from '../ui/PageHead.vue'
import SwitchField from '../ui/SwitchField.vue'
import { toast, toastError } from '../ui/toast'

const rows = ref<BackupRow[] | null>(null)
const plan = reactive<SettingsGroups['backup']>({ enabled: true, hour: 3, keep: 7 })
const planErrors = ref<Record<string, string>>({})
const working = ref('')
const message = (e: unknown, fallback = '没有成功。'): string => (e instanceof AdminError ? e.message : fallback)

async function load(): Promise<void> {
  try { rows.value = (await api.get<{ items: BackupRow[] }>('/system/backups')).items } catch (e) { toastError(message(e, '备份列表加载失败。')) }
}
onMounted(async () => {
  await load()
  try { Object.assign(plan, (await loadSettings()).groups.backup) } catch { /* the defaults stay */ }
})

async function savePlan(): Promise<void> {
  planErrors.value = {}
  working.value = 'plan'
  try { await saveGroup('backup', { ...plan }); toast('自动备份设置已保存。') } catch (e) { if (e instanceof AdminError) planErrors.value = e.fields; toastError(message(e)) } finally { working.value = '' }
}
async function backupNow(): Promise<void> {
  working.value = 'create'
  try { const row = await api.post<BackupRow>('/system/backups'); toast(`备份好了：${bytes(row.bytes)}。`); await load() } catch (e) { toastError(message(e)) } finally { working.value = '' }
}
async function save(row: BackupRow): Promise<void> {
  working.value = row.name
  try { await download(`/system/backups/${encodeURIComponent(row.name)}/download`, row.name) } catch (e) { toastError(message(e)) } finally { working.value = '' }
}
async function remove(row: BackupRow): Promise<void> {
  if (!(await confirm({ title: '删除这份备份？', text: `${row.name}（${bytes(row.bytes)}）删除后找不回来。`, confirm: '删除', danger: true }))) return
  try { await api.del(`/system/backups/${encodeURIComponent(row.name)}`); toast('已删除。'); await load() } catch (e) { toastError(message(e)) }
}

/* ---- restore ---- */
const RESTORE_TEXT = '会用这份备份里的数据替换现在网站的全部数据（文章、动态、图片、设置、账号），之后需要重新登录。恢复之前会自动再做一份“恢复前”备份，万一反悔还能回来。'
async function afterRestore(out: { restored_from: string; safety_backup: string }): Promise<void> {
  toast(`已从 ${out.restored_from} 恢复。恢复前的数据存在 ${out.safety_backup}。`)
  window.setTimeout(() => window.location.assign('/admin/'), 1200)
}
async function restore(row: BackupRow): Promise<void> {
  if (!(await confirm({ title: `从「${row.name}」恢复？`, text: RESTORE_TEXT, confirm: '恢复', danger: true, typeToConfirm: '恢复' }))) return
  working.value = row.name
  try { await afterRestore(await api.post('/system/restore', { name: row.name, confirm: 'restore' })) } catch (e) { toastError(message(e)); working.value = '' }
}
const upload = ref<HTMLInputElement | null>(null)
async function restoreFile(e: Event): Promise<void> {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (!(await confirm({ title: `用上传的「${file.name}」恢复？`, text: RESTORE_TEXT, confirm: '恢复', danger: true, typeToConfirm: '恢复' }))) return
  working.value = 'upload'
  const form = new FormData()
  form.append('file', file)
  form.append('confirm', 'restore')
  try { await afterRestore(await api.upload('/system/restore', form)) } catch (err) { toastError(message(err)); working.value = '' }
}

/* ---- Markdown export / import ---- */
interface ImportResult { posts: number; pages: number; moments: number; media: number; skipped: number; warnings: string[] }
const importResult = ref<ImportResult | null>(null)
const importInput = ref<HTMLInputElement | null>(null)
const keepStatus = ref(false)
async function exportAll(): Promise<void> {
  working.value = 'export'
  try { await download('/system/export', `markdown-export-${new Date().toISOString().slice(0, 10)}.zip`) } catch (e) { toastError(message(e)) } finally { working.value = '' }
}
async function importFile(e: Event): Promise<void> {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const text = keepStatus.value
    ? '压缩包里的 Markdown 文件会按文件里写的状态导入：写着“已发布”的会直接公开。已有的内容不会被覆盖（别名重复的会自动改名）。'
    : '压缩包里的 Markdown 文件会变成草稿文章、草稿页面和私密动态，你检查过再发布。已有的内容不会被覆盖（别名重复的会自动改名）。'
  if (!(await confirm({ title: `导入「${file.name}」？`, text, confirm: '导入' }))) return
  working.value = 'import'
  const form = new FormData()
  form.append('file', file)
  if (keepStatus.value) form.append('status', 'keep')
  try { importResult.value = await api.upload<ImportResult>('/system/import', form); toast('导入完成。') } catch (err) { toastError(message(err)) } finally { working.value = '' }
}
const label = (l: string): string => ({ manual: '手动', auto: '自动', 'pre-restore': '恢复前' } as Record<string, string>)[l] ?? l
</script>

<template>
  <div>
    <PageHead title="备份与迁移" sub="备份是一个压缩包：数据库的一致性快照加上全部图片。建议偶尔下载一份放到别的地方。">
      <button class="btn btn--fill" type="button" :disabled="!!working" @click="backupNow"><AIcon name="a-save" />{{ working === 'create' ? '正在备份……' : '立即备份' }}</button>
    </PageHead>
    <div class="adm-stack">
      <section class="adm-card adm-section" aria-labelledby="bk-h">
        <h2 id="bk-h">已有的备份</h2>
        <EmptyBox v-if="rows && !rows.length" title="还没有备份" text="点右上角“立即备份”，或者等每天的自动备份。" />
        <TableWrap v-else-if="rows" label="备份列表">
          <table class="adm-table">
            <thead><tr><th>文件</th><th>类型</th><th class="is-num">大小</th><th class="is-nowrap">时间</th><th class="is-shrink"><span class="sr-only">操作</span></th></tr></thead>
            <tbody>
              <tr v-for="r in rows" :key="r.name">
                <td class="adm-mono">{{ r.name }}</td><td><span class="adm-badge" :class="r.label === 'manual' ? '' : 'adm-badge--mist'">{{ label(r.label) }}</span></td>
                <td class="is-num">{{ bytes(r.bytes) }}</td><td class="is-nowrap" :title="when(r.created_at)">{{ ago(r.created_at) }}</td>
                <td class="is-nowrap">
                  <button class="btn btn--sm btn--ghost" type="button" :disabled="!!working" @click="save(r)"><AIcon name="a-download" />下载</button>
                  <button class="btn btn--sm btn--ghost" type="button" :disabled="!!working" @click="restore(r)">恢复</button>
                  <button class="icon-btn icon-btn--ghost" type="button" :aria-label="`删除 ${r.name}`" :disabled="!!working" @click="remove(r)"><AIcon name="a-trash" /></button>
                </td>
              </tr>
            </tbody>
          </table>
        </TableWrap>
        <div class="adm-section__foot">
          <input ref="upload" class="sr-only" type="file" accept=".gz,.tgz,application/gzip" tabindex="-1" aria-label="选择备份文件" @change="restoreFile">
          <button class="btn" type="button" :disabled="!!working" @click="upload?.click()"><AIcon name="a-upload" />用上传的备份恢复</button>
        </div>
      </section>

      <form class="adm-card adm-section" @submit.prevent="savePlan">
        <h2>自动备份</h2>
        <div class="adm-form adm-form--2">
          <SwitchField v-model="plan.enabled" label="每天自动备份" hint="维护任务每 5 分钟检查一次，到点（那个整点之后的 5 分钟内）就备份" class="span-2" />
          <Field v-slot="{ id }" label="几点备份（站点时区）" :error="planErrors.hour"><select :id="id" v-model.number="plan.hour" class="select"><option v-for="h in 24" :key="h" :value="h - 1">{{ String(h - 1).padStart(2, '0') }}:00</option></select></Field>
          <Field v-slot="{ id }" label="保留最近几份" :error="planErrors.keep" hint="1–60；更早的自动备份会被删掉，手动备份不受影响"><input :id="id" v-model.number="plan.keep" class="input" type="number" min="1" max="60"></Field>
        </div>
        <div class="adm-section__foot"><button class="btn btn--fill" type="submit" :disabled="working === 'plan'"><AIcon name="a-save" />保存</button></div>
      </form>

      <section class="adm-card adm-section" aria-labelledby="md-h">
        <h2 id="md-h">Markdown 导出与导入</h2>
        <p class="adm-hint">导出：所有文章、页面、动态变成带属性头的 <code>.md</code> 文件，图片放在 <code>media/</code> 里，打成一个压缩包——换平台或者放进 Git 都方便。导入：同样格式的压缩包（或者别处导出的普通 Markdown）。</p>
        <div class="adm-section__foot">
          <button class="btn" type="button" :disabled="!!working" @click="exportAll"><AIcon name="a-download" />{{ working === 'export' ? '正在打包……' : '导出全部内容' }}</button>
          <input ref="importInput" class="sr-only" type="file" accept=".zip,application/zip" tabindex="-1" aria-label="选择要导入的压缩包" @change="importFile">
          <button class="btn" type="button" :disabled="!!working" @click="importInput?.click()"><AIcon name="a-upload" />{{ working === 'import' ? '正在导入……' : '导入压缩包' }}</button>
        </div>
        <SwitchField v-model="keepStatus" label="保留文件里的发布状态" hint="不打开时，导入的内容全部先放进草稿（动态为私密），更保险。" />
        <div v-if="importResult" class="adm-importresult" role="status">
          <b>导入了 {{ importResult.posts }} 篇文章、{{ importResult.pages }} 个页面、{{ importResult.moments }} 条动态、{{ importResult.media }} 张图片</b><span v-if="importResult.skipped">，跳过 {{ importResult.skipped }} 项</span>。
          <ul v-if="importResult.warnings.length"><li v-for="w in importResult.warnings" :key="w">{{ w }}</li></ul>
          <RouterLink class="text-link" :to="{ path: '/posts', query: { status: 'draft' } }">去看看草稿<AIcon name="arrow-r" /></RouterLink>
        </div>
      </section>
    </div>
  </div>
</template>
