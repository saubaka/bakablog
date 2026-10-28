<script setup lang="ts">
/* The settings of one home module. `config` is edited in place (the parent owns it); `errors` are the server's messages keyed by field name. */
import { computed, ref, watch } from 'vue'
import { api } from '../../api/client'
import { fromLocalInput, toLocalInput } from '../../format'
import type { AdminPostCard, ListPage } from '../../types'
import AIcon from '../../ui/AIcon'
import Field from '../../ui/Field.vue'
import Segmented from '../../ui/Segmented.vue'
import { DOODLES } from './blocks'

type Cfg = Record<string, any>   // eslint-disable-line @typescript-eslint/no-explicit-any -- one form for five shapes; the server validates each of them
const props = defineProps<{ type: string; config: Cfg; errors: Record<string, string> }>()
const err = (path: string): string | undefined => props.errors[path]

const c = computed(() => props.config)
const buttons = computed<{ label: string; url: string; style: string }[]>(() => c.value.buttons)
function addButton(): void { if (c.value.buttons.length < 3) c.value.buttons.push({ label: '按钮', url: '/blog', style: 'line' }) }
function toggleDoodle(name: string): void {
  const list: string[] = c.value.doodles
  const at = list.indexOf(name)
  if (at >= 0) list.splice(at, 1)
  else if (list.length < 3) list.push(name)
}

/* notice: the server wants UTC, the form shows local time */
const startsAt = computed({ get: () => toLocalInput(c.value.starts_at), set: (v: string) => { c.value.starts_at = fromLocalInput(v) } })
const endsAt = computed({ get: () => toLocalInput(c.value.ends_at), set: (v: string) => { c.value.ends_at = fromLocalInput(v) } })

/* featured, by hand: pick up to six published posts */
const posts = ref<AdminPostCard[]>([])
watch(() => [props.type, c.value.mode], async () => {
  if (props.type !== 'featured' || c.value.mode !== 'manual' || posts.value.length) return
  try { posts.value = (await api.get<ListPage<AdminPostCard>>('/posts', { status: 'published', per: 100, sort: 'new' })).items } catch { posts.value = [] }
}, { immediate: true })
function togglePost(id: number): void {
  const list: number[] = c.value.post_ids
  const at = list.indexOf(id)
  if (at >= 0) list.splice(at, 1)
  else if (list.length < 6) list.push(id)
}
const modes = [{ value: 'auto', label: '自动挑选' }, { value: 'manual', label: '我来指定' }]
const layouts = [{ value: 'mixed', label: '错落卡片' }, { value: 'grid', label: '整齐网格' }, { value: 'list', label: '列表' }]
const styles = [{ value: 'fill', label: '实心' }, { value: 'line', label: '描边' }, { value: 'link', label: '文字链' }]
</script>

<template>
  <div class="adm-form adm-form--2">
    <template v-if="type === 'hero'">
      <Field v-slot="{ id }" label="小标签" :error="err('note')" hint="大标题上面的一小行，例如“近况 · 正在重画博客”"><input :id="id" v-model="c.note" class="input" maxlength="60"></Field>
      <Field label="大标题" hint="用站点名和英文名，在“外观”里修改。"><p class="adm-readonly">站点名 + 英文名</p></Field>
      <Field v-slot="{ id }" label="简介" class="span-2" :error="err('intro')"><textarea :id="id" v-model="c.intro" class="textarea" rows="3" maxlength="300" /></Field>
      <div class="span-2 adm-sub">
        <h3>按钮（最多 3 个）</h3>
        <div v-for="(b, i) in buttons" :key="i" class="adm-btnrow">
          <input v-model="b.label" class="input" maxlength="20" :aria-label="`按钮 ${i + 1} 文字`" placeholder="文字">
          <input v-model="b.url" class="input" :aria-label="`按钮 ${i + 1} 地址`" placeholder="/blog 或 https://…" spellcheck="false">
          <select v-model="b.style" class="select" :aria-label="`按钮 ${i + 1} 样式`"><option v-for="s in styles" :key="s.value" :value="s.value">{{ s.label }}</option></select>
          <button class="icon-btn icon-btn--ghost" type="button" :aria-label="`删除按钮 ${i + 1}`" @click="c.buttons.splice(i, 1)"><AIcon name="a-trash" /></button>
          <small v-if="err(`buttons.${i}.url`) || err(`buttons.${i}.label`)" class="adm-field__error" role="alert">{{ err(`buttons.${i}.url`) || err(`buttons.${i}.label`) }}</small>
        </div>
        <button v-if="c.buttons.length < 3" class="btn btn--sm btn--ghost" type="button" @click="addButton"><AIcon name="a-plus" />加一个按钮</button>
      </div>
      <Field label="装饰涂鸦（最多 3 个）" class="span-2" :error="err('doodles')">
        <div class="adm-chips" role="group" aria-label="装饰涂鸦">
          <button v-for="d in DOODLES" :key="d.value" class="adm-chip" type="button" :aria-pressed="c.doodles.includes(d.value)" @click="toggleDoodle(d.value)">{{ d.label }}</button>
        </div>
      </Field>
    </template>

    <template v-else-if="type === 'notice'">
      <Field v-slot="{ id }" label="公告内容" class="span-2" :error="err('text')" hint="留空就不显示；一行字，不要写太长"><input :id="id" v-model="c.text" class="input" maxlength="160"></Field>
      <Field v-slot="{ id }" label="开始显示（可选）" :error="err('starts_at')"><input :id="id" v-model="startsAt" class="input" type="datetime-local"></Field>
      <Field v-slot="{ id }" label="停止显示（可选）" :error="err('ends_at')"><input :id="id" v-model="endsAt" class="input" type="datetime-local"></Field>
    </template>

    <template v-else-if="type === 'featured'">
      <Field v-slot="{ id }" label="标题" :error="err('title')"><input :id="id" v-model="c.title" class="input" maxlength="30"></Field>
      <Field label="怎么选"><Segmented v-model="c.mode" label="精选方式" :options="modes" /></Field>
      <Field v-if="c.mode === 'auto'" v-slot="{ id }" label="数量" :error="err('count')" hint="取“标为精选”的文章，不够就用最新的补上"><input :id="id" v-model.number="c.count" class="input" type="number" min="1" max="6"></Field>
      <Field v-else :label="`选择文章（已选 ${c.post_ids.length}/6）`" class="span-2" :error="err('post_ids')">
        <ul class="adm-picklist">
          <li v-for="p in posts" :key="p.id"><label class="check"><input type="checkbox" :checked="c.post_ids.includes(p.id)" :disabled="!c.post_ids.includes(p.id) && c.post_ids.length >= 6" @change="togglePost(p.id)"><span>{{ p.title }}</span></label></li>
          <li v-if="!posts.length" class="adm-hint">还没有已发布的文章。</li>
        </ul>
      </Field>
    </template>

    <template v-else-if="type === 'latest_posts'">
      <Field v-slot="{ id }" label="标题" :error="err('title')"><input :id="id" v-model="c.title" class="input" maxlength="30"></Field>
      <Field v-slot="{ id }" label="数量" :error="err('count')" hint="1–12"><input :id="id" v-model.number="c.count" class="input" type="number" min="1" max="12"></Field>
      <Field v-slot="{ id }" label="一句话介绍" class="span-2" :error="err('intro')"><input :id="id" v-model="c.intro" class="input" maxlength="120"></Field>
      <Field label="排版" class="span-2"><Segmented v-model="c.layout" label="文章排版" :options="layouts" /></Field>
    </template>

    <template v-else-if="type === 'latest_moments'">
      <Field v-slot="{ id }" label="标题" :error="err('title')"><input :id="id" v-model="c.title" class="input" maxlength="30"></Field>
      <Field v-slot="{ id }" label="数量" :error="err('count')" hint="1–8"><input :id="id" v-model.number="c.count" class="input" type="number" min="1" max="8"></Field>
      <Field v-slot="{ id }" label="一句话介绍" class="span-2" :error="err('intro')"><input :id="id" v-model="c.intro" class="input" maxlength="120"></Field>
    </template>
  </div>
</template>
