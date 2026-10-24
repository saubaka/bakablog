<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { setSite } from '@/public/state'
import { applyAppearance } from '@/public/appearance'
import { fetchSite } from '@/public/data'
import { AdminError } from '../api/client'
import { loadSettings, resetGroup, saveGroup } from '../settings'
import type { SettingsGroups } from '../types'
import AIcon from '../ui/AIcon'
import { confirm } from '../ui/confirm'
import Field from '../ui/Field.vue'
import MediaField from '../ui/MediaField.vue'
import PageHead from '../ui/PageHead.vue'
import Segmented from '../ui/Segmented.vue'
import SwitchField from '../ui/SwitchField.vue'
import { toast, toastError } from '../ui/toast'

const loaded = ref(false)
const site = reactive<SettingsGroups['site']>({ name: '', name_en: '', tagline: '', description: '', language: 'zh-CN', timezone: 'Asia/Shanghai', logo_media_id: null, favicon_media_id: null })
const author = reactive<SettingsGroups['author']>({ name: '', bio: '', avatar_media_id: null, links: [] })
const look = reactive<SettingsGroups['appearance']>({ theme: 'default', decor: { tape: true, doodles: true }, motion: 'full', code_theme: 'frost', texts: { not_found_title: '', not_found_text: '', error_title: '', error_text: '' } })
const errors = reactive<Record<string, Record<string, string>>>({ site: {}, author: {}, appearance: {} })
const busy = reactive<Record<string, boolean>>({})
const TZ = ['Asia/Shanghai', 'Asia/Tokyo', 'Asia/Singapore', 'Asia/Hong_Kong', 'Asia/Taipei', 'Europe/London', 'Europe/Berlin', 'America/New_York', 'America/Los_Angeles', 'Australia/Sydney', 'Pacific/Auckland', 'UTC']
const themes = [{ id: 'default', name: '糖霜', text: '均衡，默认', swatch: ['#f7fbff', '#e6f1fc', '#fdeef3'] }, { id: 'sky', name: '晴空', text: '蓝为主', swatch: ['#f3f9ff', '#e3effb', '#e3effb'] }, { id: 'sakura', name: '樱花', text: '粉为主', swatch: ['#fff8fb', '#fdeaf1', '#e6f1fc'] }, { id: 'fog', name: '云雾', text: '灰为主', swatch: ['#f8f9fb', '#e9eef5', '#eceff4'] }]
const motionOptions = [{ value: 'full', label: '标准', hint: '滚动时元素逐个入场' }, { value: 'soft', label: '轻柔', hint: '位移更小' }, { value: 'off', label: '关闭', hint: '没有入场动效' }]
const codeOptions = [{ value: 'frost', label: '糖霜' }, { value: 'blossom', label: '粉墨' }, { value: 'fog', label: '雾灰' }]
const linkKinds = [{ value: 'mail', label: '邮箱' }, { value: 'rss', label: '订阅' }, { value: 'link', label: '链接' }]

function fill(g: SettingsGroups): void {
  Object.assign(site, JSON.parse(JSON.stringify(g.site)))
  Object.assign(author, JSON.parse(JSON.stringify(g.author)))
  Object.assign(look, JSON.parse(JSON.stringify(g.appearance)))
}
onMounted(async () => { try { fill((await loadSettings()).groups); loaded.value = true } catch (e) { toastError(e instanceof AdminError ? e.message : '设置加载失败。') } })

async function save(group: 'site' | 'author' | 'appearance'): Promise<void> {
  busy[group] = true
  errors[group] = {}
  try {
    const values = group === 'site' ? { ...site } : group === 'author' ? { ...author, links: author.links.filter((l) => l.label.trim() && l.url.trim()) } : { ...look }
    await saveGroup(group, values)
    toast('已保存。前台刷新后生效。')
    try { const s = await fetchSite(); setSite(s); applyAppearance(s) } catch { /* the admin keeps working */ }
  } catch (e) {
    if (e instanceof AdminError) { errors[group] = e.fields; toastError(e.firstField ? `${e.message}（${e.firstField}）` : e.message) } else toastError('保存没有成功。')
  } finally { busy[group] = false }
}
async function reset(group: 'appearance'): Promise<void> {
  if (!(await confirm({ title: '恢复默认外观？', text: '主题、装饰、动效、代码高亮和 404 / 500 文案都会回到默认值。', confirm: '恢复默认', danger: true }))) return
  try { Object.assign(look, JSON.parse(JSON.stringify(await resetGroup(group)))); toast('已恢复默认外观。') } catch (e) { toastError(e instanceof AdminError ? e.message : '没有成功。') }
}
const addLink = (): void => { if (author.links.length < 8) author.links.push({ label: '', kind: 'link', url: '' }) }
</script>

<template>
  <div>
    <PageHead title="外观" sub="站点信息、作者、主题和文案。主题只能在四套浅色预设里选——这样怎么调都不会变成深色。" />
    <p v-if="!loaded" class="adm-boot" role="status">正在加载设置……</p>
    <div v-else class="adm-stack">
      <form class="adm-card adm-section" @submit.prevent="save('site')">
        <h2>站点信息</h2>
        <div class="adm-form adm-form--2">
          <Field v-slot="{ id }" label="站点名" required :error="errors.site?.name"><input :id="id" v-model="site.name" class="input" maxlength="60"></Field>
          <Field v-slot="{ id }" label="英文名" :error="errors.site?.name_en" hint="顶栏小字、标签页标题里用"><input :id="id" v-model="site.name_en" class="input" maxlength="60"></Field>
          <Field v-slot="{ id }" label="一句话简介（副标题）" :error="errors.site?.tagline"><input :id="id" v-model="site.tagline" class="input" maxlength="80"></Field>
          <Field v-slot="{ id }" label="语言" :error="errors.site?.language" hint="比如 zh-CN、en、ja"><input :id="id" v-model="site.language" class="input" maxlength="10"></Field>
          <Field v-slot="{ id }" label="站点描述" class="span-2" :error="errors.site?.description" hint="搜索结果和分享卡片里的默认描述"><textarea :id="id" v-model="site.description" class="textarea" rows="2" maxlength="300" /></Field>
          <Field v-slot="{ id }" label="时区" :error="errors.site?.timezone" hint="“某天”“某月”由它决定，比如文章归在哪个月"><input :id="id" v-model="site.timezone" class="input" list="adm-tz" spellcheck="false"><datalist id="adm-tz"><option v-for="z in TZ" :key="z" :value="z" /></datalist></Field>
          <span />
          <Field label="站点标志（可选）" hint="显示在顶栏左边，建议横向的透明背景图；不选就只显示站名"><MediaField v-model="site.logo_media_id" title="选择标志" /></Field>
          <Field label="网站图标 favicon（可选）" hint="浏览器标签页上的小图标"><MediaField v-model="site.favicon_media_id" title="选择图标" /></Field>
        </div>
        <div class="adm-section__foot"><button class="btn btn--fill" type="submit" :disabled="busy.site"><AIcon name="a-save" />保存站点信息</button></div>
      </form>

      <form class="adm-card adm-section" @submit.prevent="save('author')">
        <h2>作者与社交链接</h2>
        <div class="adm-form adm-form--2">
          <Field v-slot="{ id }" label="作者名" required :error="errors.author?.name"><input :id="id" v-model="author.name" class="input" maxlength="40"></Field>
          <Field label="头像" hint="首页“关于”卡片、文章底部的作者小卡片"><MediaField v-model="author.avatar_media_id" title="选择头像" /></Field>
          <Field v-slot="{ id }" label="简介" class="span-2" :error="errors.author?.bio"><textarea :id="id" v-model="author.bio" class="textarea" rows="3" maxlength="600" /></Field>
        </div>
        <div class="adm-links">
          <h3 class="adm-h3">链接（邮箱、订阅、社交主页，最多 8 个）</h3>
          <div v-for="(l, i) in author.links" :key="i" class="adm-linkrow">
            <input v-model="l.label" class="input" :aria-label="`第 ${i + 1} 个链接的名字`" placeholder="名字，如：发邮件" maxlength="20">
            <select v-model="l.kind" class="select" :aria-label="`第 ${i + 1} 个链接的类型`"><option v-for="k in linkKinds" :key="k.value" :value="k.value">{{ k.label }}</option></select>
            <input v-model="l.url" class="input" :aria-label="`第 ${i + 1} 个链接的地址`" placeholder="mailto:… / https://… / /feed/posts.xml" spellcheck="false">
            <button class="icon-btn icon-btn--ghost" type="button" :aria-label="`删除第 ${i + 1} 个链接`" @click="author.links.splice(i, 1)"><AIcon name="a-trash" /></button>
          </div>
          <p v-if="errors.author?.links" class="adm-field__error">{{ errors.author.links }}</p>
          <button class="btn btn--sm btn--ghost" type="button" :disabled="author.links.length >= 8" @click="addLink"><AIcon name="a-plus" />加一个链接</button>
        </div>
        <div class="adm-section__foot"><button class="btn btn--fill" type="submit" :disabled="busy.author"><AIcon name="a-save" />保存作者信息</button></div>
      </form>

      <form class="adm-card adm-section" @submit.prevent="save('appearance')">
        <h2>主题与动效</h2>
        <fieldset class="adm-themes"><legend class="label">主题</legend>
          <label v-for="t in themes" :key="t.id" class="adm-theme" :class="{ 'is-on': look.theme === t.id }">
            <input v-model="look.theme" type="radio" name="theme" :value="t.id"><span class="adm-theme__sw"><i v-for="c in t.swatch" :key="c" :style="{ backgroundColor: c }" /></span><b>{{ t.name }}</b><small>{{ t.text }}</small>
          </label>
        </fieldset>
        <div class="adm-form adm-form--2">
          <Field label="滚动动效（访客的默认值）" hint="访客系统里开了“减少动态效果”时，一律关闭。"><Segmented v-model="look.motion" label="动效强度" :options="motionOptions" /></Field>
          <Field label="代码高亮"><Segmented v-model="look.code_theme" label="代码高亮" :options="codeOptions" /></Field>
          <div class="adm-switches span-2"><SwitchField v-model="look.decor.tape" label="和纸胶带" hint="卡片、便签上的小胶带" /><SwitchField v-model="look.decor.doodles" label="涂鸦" hint="首页开场的小星星、爱心" /></div>
        </div>
        <h2 class="adm-section__sub">404 与出错页的文案</h2>
        <div class="adm-form adm-form--2">
          <Field v-slot="{ id }" label="找不到页面：标题"><input :id="id" v-model="look.texts.not_found_title" class="input" maxlength="40"></Field>
          <Field v-slot="{ id }" label="找不到页面：一句话"><input :id="id" v-model="look.texts.not_found_text" class="input" maxlength="200"></Field>
          <Field v-slot="{ id }" label="服务器出错：标题"><input :id="id" v-model="look.texts.error_title" class="input" maxlength="40"></Field>
          <Field v-slot="{ id }" label="服务器出错：一句话"><input :id="id" v-model="look.texts.error_text" class="input" maxlength="200"></Field>
        </div>
        <div class="adm-section__foot"><button class="btn btn--ghost" type="button" @click="reset('appearance')">恢复默认</button><button class="btn btn--fill" type="submit" :disabled="busy.appearance"><AIcon name="a-save" />保存外观</button></div>
      </form>
    </div>
  </div>
</template>
