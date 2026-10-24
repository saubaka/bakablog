<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { api, AdminError } from '../api/client'
import type { AdminTag } from '../types'
import AIcon from '../ui/AIcon'
import { confirm } from '../ui/confirm'
import EmptyBox from '../ui/EmptyBox.vue'
import Field from '../ui/Field.vue'
import IconPicker from '../ui/IconPicker.vue'
import Modal from '../ui/Modal.vue'
import TableWrap from '../ui/TableWrap.vue'
import PageHead from '../ui/PageHead.vue'
import Segmented from '../ui/Segmented.vue'
import { toast, toastError } from '../ui/toast'
import { useSubmit } from '../use'

const tags = ref<AdminTag[]>([])
const loading = ref(true)
const q = ref('')
const selected = ref<Set<number>>(new Set())
const editing = ref<AdminTag | 'new' | null>(null)
const mergeOpen = ref(false)
const mergeTarget = ref<number | ''>('')
const form = reactive({ name: '', slug: '', color: 'sky' as 'sky' | 'rose' | 'mist' | 'white', sticker: null as string | null, description: '' })
const { busy, fields, run } = useSubmit()
const shown = computed(() => { const t = q.value.trim().toLowerCase(); return t ? tags.value.filter((x) => `${x.name} ${x.slug}`.toLowerCase().includes(t)) : tags.value })
const unused = computed(() => tags.value.filter((t) => !t.post_count && !t.moment_count).length)
const colors = [{ value: 'sky', label: '浅蓝' }, { value: 'rose', label: '浅粉' }, { value: 'mist', label: '浅灰' }, { value: 'white', label: '白' }]

async function load(): Promise<void> {
  loading.value = true
  try { tags.value = (await api.get<{ items: AdminTag[] }>('/taxonomy/tags')).items; selected.value = new Set() } catch (e) { toastError(e instanceof AdminError ? e.message : '标签加载失败。') } finally { loading.value = false }
}
onMounted(load)
const toggle = (id: number): void => { const s = new Set(selected.value); if (s.has(id)) s.delete(id); else s.add(id); selected.value = s }

function open(t: AdminTag | 'new'): void {
  editing.value = t
  Object.assign(form, t === 'new' ? { name: '', slug: '', color: 'sky', sticker: null, description: '' } : { name: t.name, slug: t.slug, color: t.color, sticker: t.sticker, description: t.description })
}
async function save(): Promise<void> {
  const target = editing.value
  try {
    await run(async () => {
      const body = { name: form.name.trim(), color: form.color, sticker: form.sticker, description: form.description.trim(), ...(form.slug.trim() ? { slug: form.slug.trim() } : {}) }
      if (target === 'new') await api.post('/taxonomy/tags', body)
      else if (target) await api.patch(`/taxonomy/tags/${target.id}`, body)
    })
    toast('标签已保存。')
    editing.value = null
    await load()
  } catch (e) { if (!(e instanceof AdminError && e.status === 422)) toastError(e instanceof AdminError ? e.message : '保存没有成功。') }
}
async function remove(t: AdminTag): Promise<void> {
  if (!(await confirm({ title: `删除标签「${t.name}」？`, text: t.post_count + t.moment_count ? `它在 ${t.post_count} 篇文章和 ${t.moment_count} 条动态上，删除后只是去掉标签，内容本身不会删。` : '没有内容用到它。', confirm: '删除标签', danger: true }))) return
  try { await api.del(`/taxonomy/tags/${t.id}`); toast('标签已删除。'); await load() } catch (e) { toastError(e instanceof AdminError ? e.message : '删除没有成功。') }
}
async function cleanup(): Promise<void> {
  if (!(await confirm({ title: '清理没用的标签？', text: `会删除 ${unused.value} 个没有任何文章或动态用到的标签。`, confirm: '清理', danger: true }))) return
  try { const r = await api.post<{ deleted: number }>('/taxonomy/tags/cleanup'); toast(`已清理 ${r.deleted ?? unused.value} 个标签。`); await load() } catch (e) { toastError(e instanceof AdminError ? e.message : '清理没有成功。') }
}
async function merge(): Promise<void> {
  if (mergeTarget.value === '') return
  const sources = [...selected.value].filter((id) => id !== mergeTarget.value)
  try {
    await api.post('/taxonomy/tags/merge', { source_ids: sources, target_id: mergeTarget.value })
    toast('标签已合并。')
    mergeOpen.value = false
    await load()
  } catch (e) { toastError(e instanceof AdminError ? e.message : '合并没有成功。') }
}
</script>

<template>
  <div>
    <PageHead title="标签" sub="标签用来横着串起文章和动态。">
      <button v-if="unused" class="btn btn--ghost" type="button" @click="cleanup"><AIcon name="a-trash" />清理 {{ unused }} 个没用的</button>
      <button class="btn btn--fill" type="button" @click="open('new')"><AIcon name="a-plus" />新建标签</button>
    </PageHead>
    <div class="adm-toolbar">
      <div class="searchfield"><AIcon name="search" /><input v-model="q" class="input" type="search" placeholder="搜标签" aria-label="搜索标签"></div>
      <span class="adm-toolbar__grow" />
      <template v-if="selected.size > 1"><button class="btn btn--sm" type="button" @click="mergeTarget = ''; mergeOpen = true">合并所选的 {{ selected.size }} 个</button></template>
    </div>
    <EmptyBox v-if="!loading && !tags.length" title="还没有标签" text="写文章或发动态时顺手打上标签，这里就有了。" />
    <TableWrap v-else label="标签列表">
      <table class="adm-table">
        <thead><tr><th class="is-shrink"><span class="sr-only">选择</span></th><th>标签</th><th>别名</th><th class="is-num">文章</th><th class="is-num">动态</th><th class="is-shrink"><span class="sr-only">操作</span></th></tr></thead>
        <tbody>
          <tr v-for="t in shown" :key="t.id">
            <td><label class="check"><input type="checkbox" :checked="selected.has(t.id)" :aria-label="`选择标签：${t.name}`" @change="toggle(t.id)"><span class="check__box"><AIcon name="check" /></span></label></td>
            <td><span class="tag" :class="t.color === 'white' ? '' : `tag--${t.color}`"><AIcon v-if="t.sticker" :name="t.sticker" />{{ t.name }}</span></td>
            <td class="adm-mono">{{ t.slug }}</td><td class="is-num">{{ t.post_count }}</td><td class="is-num">{{ t.moment_count }}</td>
            <td class="is-nowrap"><button class="btn btn--sm btn--ghost" type="button" @click="open(t)"><AIcon name="a-edit" />编辑</button><button class="icon-btn icon-btn--ghost" type="button" :aria-label="`删除标签：${t.name}`" @click="remove(t)"><AIcon name="a-trash" /></button></td>
          </tr>
        </tbody>
      </table>
    </TableWrap>

    <Modal :open="editing !== null" :title="editing === 'new' ? '新建标签' : '编辑标签'" @close="editing = null">
      <form class="adm-form" @submit.prevent="save">
        <Field v-slot="{ id }" label="名称" required :error="fields.name"><input :id="id" v-model="form.name" class="input" maxlength="40" data-autofocus></Field>
        <Field v-slot="{ id }" label="别名" :error="fields.slug" hint="留空自动生成。"><input :id="id" v-model="form.slug" class="input" spellcheck="false"></Field>
        <Field label="颜色"><Segmented v-model="form.color" label="标签颜色" :options="colors" /></Field>
        <Field label="贴纸图标"><IconPicker v-model="form.sticker" label="标签图标" /></Field>
        <Field v-slot="{ id }" label="说明（可选）"><textarea :id="id" v-model="form.description" class="textarea" rows="2" maxlength="300" /></Field>
      </form>
      <template #footer><button class="btn btn--ghost" type="button" @click="editing = null">取消</button><button class="btn btn--fill" type="button" :disabled="busy || !form.name.trim()" @click="save">保存</button></template>
    </Modal>

    <Modal :open="mergeOpen" title="合并标签" @close="mergeOpen = false">
      <p>把所选的 {{ selected.size }} 个标签合成一个：用到它们的文章和动态都会改成“保留的标签”，其余标签被删除。</p>
      <Field v-slot="{ id }" label="保留哪一个"><select :id="id" v-model="mergeTarget" class="select" data-autofocus><option value="">请选择……</option><option v-for="t in tags.filter((x) => selected.has(x.id))" :key="t.id" :value="t.id">{{ t.name }}（{{ t.post_count + t.moment_count }}）</option></select></Field>
      <template #footer><button class="btn btn--ghost" type="button" @click="mergeOpen = false">取消</button><button class="btn btn--fill" type="button" :disabled="mergeTarget === ''" @click="merge">合并</button></template>
    </Modal>
  </div>
</template>
