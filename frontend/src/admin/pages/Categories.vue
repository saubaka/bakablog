<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { api, AdminError } from '../api/client'
import { loadTaxonomy, taxo } from '../taxonomy'
import type { AdminCategory } from '../types'
import AIcon from '../ui/AIcon'
import { confirm } from '../ui/confirm'
import EmptyBox from '../ui/EmptyBox.vue'
import Field from '../ui/Field.vue'
import IconPicker from '../ui/IconPicker.vue'
import Modal from '../ui/Modal.vue'
import PageHead from '../ui/PageHead.vue'
import SwitchField from '../ui/SwitchField.vue'
import { useSortable } from '../ui/sortable'
import { toast, toastError } from '../ui/toast'
import { debounced, useSubmit } from '../use'

const list = ref<AdminCategory[]>([])
const loading = ref(true)
const editing = ref<AdminCategory | 'new' | null>(null)
const removing = ref<AdminCategory | null>(null)
const reassign = ref<number | ''>('')
const form = reactive({ name: '', slug: '', description: '', sticker: null as string | null, show_on_shelf: true })
const { busy, fields, run } = useSubmit()
const sort = useSortable(() => list.value, (n) => { list.value = n })

async function load(): Promise<void> {
  loading.value = true
  try { await loadTaxonomy(true); list.value = [...taxo.categories] } catch (e) { toastError(e instanceof AdminError ? e.message : '分类加载失败。') } finally { loading.value = false }
}
onMounted(load)

const reorder = debounced(async () => {
  try { await api.post('/taxonomy/categories/reorder', { ids: list.value.map((c) => c.id) }); toast('顺序已保存。') } catch (e) { toastError(e instanceof AdminError ? e.message : '排序没有保存成功。'); await load() }
}, 700)
let ready = false
watch(() => list.value.map((c) => c.id).join(','), () => { if (ready) reorder(); else ready = true })

function open(c: AdminCategory | 'new'): void {
  editing.value = c
  Object.assign(form, c === 'new' ? { name: '', slug: '', description: '', sticker: null, show_on_shelf: true } : { name: c.name, slug: c.slug, description: c.description, sticker: c.sticker, show_on_shelf: c.show_on_shelf })
}
async function save(): Promise<void> {
  const target = editing.value
  try {
    await run(async () => {
      const body = { name: form.name.trim(), description: form.description.trim(), sticker: form.sticker, show_on_shelf: form.show_on_shelf, ...(form.slug.trim() ? { slug: form.slug.trim() } : {}) }
      if (target === 'new') await api.post('/taxonomy/categories', body)
      else if (target) await api.patch(`/taxonomy/categories/${target.id}`, body)
    })
    toast('分类已保存。')
    editing.value = null
    await load()
  } catch (e) { if (!(e instanceof AdminError && e.status === 422)) toastError(e instanceof AdminError ? e.message : '保存没有成功。') }
}
async function toggleShelf(c: AdminCategory): Promise<void> {
  try { await api.patch(`/taxonomy/categories/${c.id}`, { show_on_shelf: !c.show_on_shelf }); c.show_on_shelf = !c.show_on_shelf } catch (e) { toastError(e instanceof AdminError ? e.message : '没有成功。') }
}
function ask(c: AdminCategory): void { removing.value = c; reassign.value = '' }
async function remove(): Promise<void> {
  const c = removing.value
  if (!c) return
  if (c.count && reassign.value === '') { toastError('请选择这些文章改归到哪个分类。'); return }
  try {
    await api.del(`/taxonomy/categories/${c.id}`, c.count ? { reassign_to: reassign.value } : undefined)
    toast('分类已删除。')
    removing.value = null
    await load()
  } catch (e) { toastError(e instanceof AdminError ? e.message : '删除没有成功。') }
}
void confirm
</script>

<template>
  <div>
    <PageHead title="分类" sub="一篇文章只属于一个分类。拖动左边的把手，或在把手上按 ↑ ↓，调整它们在前台的顺序。">
      <button class="btn btn--fill" type="button" @click="open('new')"><AIcon name="a-plus" />新建分类</button>
    </PageHead>
    <EmptyBox v-if="!loading && !list.length" title="还没有分类" text="分类像书架上的隔板，先建一个吧。" />
    <ul v-else class="adm-sortlist">
      <li v-for="(c, i) in list" :key="c.id" class="adm-sortrow" :class="{ 'is-dragging': sort.dragging.value === i }" data-sort-row>
        <button class="adm-grip" type="button" :aria-label="`拖动调整「${c.name}」的顺序`" v-bind="sort.handle(i)"><AIcon name="a-grip" /></button>
        <span class="adm-sortrow__ico"><AIcon :name="c.sticker || 'folder'" /></span>
        <span class="adm-sortrow__main"><b>{{ c.name }}</b><small>/category/{{ c.slug }} · {{ c.count }} 篇<template v-if="c.public_count !== c.count">（公开 {{ c.public_count }}）</template></small></span>
        <label class="switch adm-sortrow__switch" :title="c.show_on_shelf ? '博客页的分类页签上显示' : '博客页的分类页签上不显示'"><input type="checkbox" role="switch" :checked="c.show_on_shelf" :aria-label="`「${c.name}」出现在首页书架`" @change="toggleShelf(c)"><span class="switch__track" aria-hidden="true" /><span class="adm-sortrow__swl">书架</span></label>
        <button class="btn btn--sm btn--ghost" type="button" @click="open(c)"><AIcon name="a-edit" />编辑</button>
        <button class="icon-btn icon-btn--ghost" type="button" :aria-label="`删除「${c.name}」`" @click="ask(c)"><AIcon name="a-trash" /></button>
      </li>
    </ul>
    <p class="sr-only" role="status" aria-live="polite">{{ sort.announce.value }}</p>

    <Modal :open="editing !== null" :title="editing === 'new' ? '新建分类' : '编辑分类'" @close="editing = null">
      <form class="adm-form" @submit.prevent="save">
        <Field v-slot="{ id }" label="名称" required :error="fields.name"><input :id="id" v-model="form.name" class="input" maxlength="60" data-autofocus></Field>
        <Field v-slot="{ id }" label="别名" :error="fields.slug" hint="网址的一部分，留空自动生成。改了别名，旧地址会自动跳到新地址。"><input :id="id" v-model="form.slug" class="input" spellcheck="false"></Field>
        <Field v-slot="{ id }" label="说明" :error="fields.description" hint="显示在分类页的标题下面。"><textarea :id="id" v-model="form.description" class="textarea" rows="2" maxlength="500" /></Field>
        <Field label="贴纸图标"><IconPicker v-model="form.sticker" label="分类图标" /></Field>
        <SwitchField v-model="form.show_on_shelf" label="出现在博客页的分类页签里" />
      </form>
      <template #footer><button class="btn btn--ghost" type="button" @click="editing = null">取消</button><button class="btn btn--fill" type="button" :disabled="busy || !form.name.trim()" @click="save">保存</button></template>
    </Modal>

    <Modal :open="removing !== null" title="删除分类" @close="removing = null">
      <p v-if="removing && !removing.count">删除「{{ removing.name }}」。它下面没有文章，不会影响任何内容。</p>
      <template v-else-if="removing">
        <p>「{{ removing.name }}」下面有 {{ removing.count }} 篇文章。删除前，请选择它们改归到哪里：</p>
        <select v-model="reassign" class="select" aria-label="改归到" data-autofocus><option value="">请选择……</option><option v-for="c in list.filter((x) => x.id !== removing?.id)" :key="c.id" :value="c.id">{{ c.name }}</option></select>
      </template>
      <template #footer><button class="btn btn--ghost" type="button" @click="removing = null">取消</button><button class="btn btn--danger" type="button" @click="remove">删除分类</button></template>
    </Modal>
  </div>
</template>
