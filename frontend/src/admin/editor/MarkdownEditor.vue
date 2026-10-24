<script setup lang="ts">
/* The Markdown source editor: a plain <textarea> (so the browser's own undo, spell-check and Chinese / Japanese input methods work exactly as
   everywhere else) with a toolbar, keyboard shortcuts, list continuation, and pictures that can be pasted or dropped.
   Edits go through execCommand("insertText") so Undo / Redo keep working after a toolbar action. */
import { ref } from 'vue'
import AIcon from '../ui/AIcon'
import Menu from '../ui/Menu.vue'
import { toast, toastError } from '../ui/toast'
import { callout, codeFence, continueList, diff, footnote, images, indent, link, rule, table, toggleBlock, wrap, type Sel } from './textedit'

const props = withDefaults(defineProps<{ placeholder?: string; upload?: (file: File) => Promise<{ id: number; alt: string }>; compact?: boolean; id?: string; label?: string }>(), { placeholder: '', upload: undefined, compact: false, id: undefined, label: 'Markdown 正文' })
const model = defineModel<string>({ required: true })
const emit = defineEmits<{ pickImage: [mode: 'one' | 'gallery']; save: []; scroll: [ratio: number] }>()
const ta = ref<HTMLTextAreaElement | null>(null)
const busy = ref(0)

const read = (): Sel => ({ value: ta.value?.value ?? '', start: ta.value?.selectionStart ?? 0, end: ta.value?.selectionEnd ?? 0 })

function write(next: Sel): void {
  const el = ta.value
  if (!el) return
  const cur = read()
  el.focus()
  if (next.value !== cur.value) {
    const d = diff(cur.value, next.value)
    el.setSelectionRange(d.from, d.to)
    const ok = d.inserted === '' ? document.execCommand('delete') : document.execCommand('insertText', false, d.inserted)
    if (!ok || el.value !== next.value) {             // execCommand is unavailable or refused: edit directly (undo history is lost for this step)
      el.value = next.value
      el.dispatchEvent(new Event('input', { bubbles: true }))
    }
  }
  el.setSelectionRange(next.start, next.end)
}
const run = (fn: (s: Sel) => Sel | null): void => { const next = fn(read()); if (next) write(next) }

/** Insert pictures chosen in the library (called by the page after the picker closes). */
function insertImages(items: { id: number; alt: string }[], polaroid = false): void {
  if (!items.length) return
  run((s) => images(s, items, polaroid))
}

async function uploadAll(files: File[]): Promise<void> {
  if (!props.upload) return
  const pictures = files.filter((f) => f.type.startsWith('image/'))
  if (!pictures.length) return
  busy.value += pictures.length
  const done: { id: number; alt: string }[] = []
  for (const f of pictures) {
    try { done.push(await props.upload(f)) } catch (e) { toastError(`${f.name || '图片'}：${e instanceof Error ? e.message : '上传失败'}`) } finally { busy.value -= 1 }
  }
  if (done.length) { insertImages(done); toast(`已插入 ${done.length} 张图片。`) }
}

function onPaste(e: ClipboardEvent): void {
  const files = [...(e.clipboardData?.files ?? [])]
  if (files.length) { e.preventDefault(); void uploadAll(files); return }
  const text = e.clipboardData?.getData('text/plain') ?? ''
  const s = read()
  if (s.start !== s.end && /^https?:\/\/\S+$/.test(text.trim())) { e.preventDefault(); write(link(s, text.trim())) }   // paste a URL over a selection: make it a link
}
function onDrop(e: DragEvent): void {
  const files = [...(e.dataTransfer?.files ?? [])]
  if (files.length) { e.preventDefault(); void uploadAll(files) }
}

function onKey(e: KeyboardEvent): void {
  const mod = e.metaKey || e.ctrlKey
  const k = e.key.toLowerCase()
  if (mod && k === 's') { e.preventDefault(); emit('save'); return }
  if (mod && !e.shiftKey && k === 'b') { e.preventDefault(); run((s) => wrap(s, '**', '**', '粗体')); return }
  if (mod && !e.shiftKey && k === 'i') { e.preventDefault(); run((s) => wrap(s, '*', '*', '斜体')); return }
  if (mod && e.shiftKey && k === 'x') { e.preventDefault(); run((s) => wrap(s, '~~', '~~', '删除线')); return }
  if (e.key === 'Enter' && !e.shiftKey && !mod && !e.isComposing) {
    const next = continueList(read())
    if (next) { e.preventDefault(); write(next) }
    return
  }
  if (e.key === 'Tab' && !mod && !e.altKey && !e.isComposing) {
    const s = read()
    const onList = /^\s*([-*+]|\d+[.)])\s/.test(s.value.slice(s.value.lastIndexOf('\n', s.start - 1) + 1))
    if (s.start !== s.end && s.value.slice(s.start, s.end).includes('\n') || onList) { e.preventDefault(); write(indent(s, e.shiftKey)) }
  }
}

function onScroll(): void {
  const el = ta.value
  if (!el) return
  const max = el.scrollHeight - el.clientHeight
  emit('scroll', max > 0 ? el.scrollTop / max : 0)
}

function setScroll(ratio: number): void {
  const el = ta.value
  if (el) el.scrollTop = ratio * (el.scrollHeight - el.clientHeight)
}

defineExpose({ focus: () => ta.value?.focus(), insertImages, setScroll, element: ta })
</script>

<template>
  <div class="adm-md" :class="{ 'is-compact': compact }">
    <div class="adm-md__bar" role="toolbar" aria-label="格式工具条">
      <Menu label="标题" icon="a-heading" icon-only align="start">
        <button role="menuitem" type="button" @click="run((s) => toggleBlock(s, 'h2'))">二级标题 ##</button>
        <button role="menuitem" type="button" @click="run((s) => toggleBlock(s, 'h3'))">三级标题 ###</button>
        <button role="menuitem" type="button" @click="run((s) => toggleBlock(s, 'h4'))">四级标题 ####</button>
      </Menu>
      <button type="button" class="adm-md__b" title="粗体（Ctrl/⌘ B）" aria-label="粗体" @click="run((s) => wrap(s, '**', '**', '粗体'))"><AIcon name="a-bold" /></button>
      <button type="button" class="adm-md__b" title="斜体（Ctrl/⌘ I）" aria-label="斜体" @click="run((s) => wrap(s, '*', '*', '斜体'))"><AIcon name="a-italic" /></button>
      <button type="button" class="adm-md__b" title="删除线" aria-label="删除线" @click="run((s) => wrap(s, '~~', '~~', '删除线'))"><AIcon name="a-strike" /></button>
      <button type="button" class="adm-md__b" title="行内代码" aria-label="行内代码" @click="run((s) => wrap(s, '`', '`', '代码'))"><AIcon name="a-code" /></button>
      <span class="adm-md__sep" aria-hidden="true" />
      <button type="button" class="adm-md__b" title="引用" aria-label="引用" @click="run((s) => toggleBlock(s, 'quote'))"><AIcon name="quote" /></button>
      <button type="button" class="adm-md__b" title="无序列表" aria-label="无序列表" @click="run((s) => toggleBlock(s, 'bullet'))"><AIcon name="a-ul" /></button>
      <button type="button" class="adm-md__b" title="有序列表" aria-label="有序列表" @click="run((s) => toggleBlock(s, 'ordered'))"><AIcon name="a-ol" /></button>
      <button type="button" class="adm-md__b" title="任务列表" aria-label="任务列表" @click="run((s) => toggleBlock(s, 'task'))"><AIcon name="a-task" /></button>
      <span class="adm-md__sep" aria-hidden="true" />
      <button type="button" class="adm-md__b" title="链接" aria-label="链接" @click="run((s) => link(s, 'https://'))"><AIcon name="a-link" /></button>
      <button type="button" class="adm-md__b" title="插入图片（也可以直接粘贴或拖进来）" aria-label="插入图片" @click="emit('pickImage', 'one')"><AIcon name="a-image" /></button>
      <button type="button" class="adm-md__b" title="图集（连续几张图片）" aria-label="图集" @click="emit('pickImage', 'gallery')"><AIcon name="a-gallery" /></button>
      <span class="adm-md__sep" aria-hidden="true" />
      <button type="button" class="adm-md__b" title="代码块" aria-label="代码块" @click="run((s) => codeFence(s, 'python'))"><AIcon name="code" /></button>
      <button type="button" class="adm-md__b" title="表格" aria-label="表格" @click="run((s) => table(s))"><AIcon name="a-table" /></button>
      <Menu label="提示块" icon="a-callout" icon-only align="start">
        <button role="menuitem" type="button" @click="run((s) => callout(s, 'tip'))">小提示（蓝）</button>
        <button role="menuitem" type="button" @click="run((s) => callout(s, 'note'))">备注（灰）</button>
        <button role="menuitem" type="button" @click="run((s) => callout(s, 'warn'))">小心（粉）</button>
        <button role="menuitem" type="button" @click="run((s) => callout(s, 'love'))">喜欢（粉）</button>
      </Menu>
      <button type="button" class="adm-md__b" title="脚注" aria-label="脚注" @click="run((s) => footnote(s))"><AIcon name="a-footnote" /></button>
      <button type="button" class="adm-md__b" title="分隔线" aria-label="分隔线" @click="run((s) => rule(s))"><AIcon name="a-hr" /></button>
      <span v-if="busy" class="adm-md__busy" role="status">正在上传 {{ busy }} 张图片……</span>
    </div>
    <textarea :id="id" ref="ta" v-model="model" class="adm-md__area" spellcheck="false" :placeholder="placeholder" :aria-label="label" @keydown="onKey" @paste="onPaste" @drop="onDrop" @dragover.prevent @scroll.passive="onScroll" />
  </div>
</template>
