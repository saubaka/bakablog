<script setup lang="ts">
/* The body of an article, a page or a moment: HTML the server has already sanitised (Markdown pipeline + allow-list), put in as is.
   This component adds what plain HTML cannot do: scroll motion for the top-level blocks, a copy button on code,
   a picture viewer, quiet placeholders for pictures that are still loading, and in-app navigation for internal links. */
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { adopt, release } from '@/fx/engine'
import { copyText } from '@/shared/clipboard'
import { labelTasks, markScrollable } from '@/shared/prose'
import { splitHeading } from '@/fx/domsplit'
import { openLightbox, type LightboxItem } from '../lightbox'
import { internalLink } from '../links'
import { useViewport } from '../viewport'

const props = withDefaults(defineProps<{ html: string; blocks?: boolean; articleClass?: string }>(), { blocks: true, articleClass: '' })
const root = ref<HTMLElement | null>(null)
const router = useRouter()
const { narrow } = useViewport()
let copyTimer = 0

/** Motion hint for each top-level block (the CSS in ui/css/fx.css defines what each type does). */
function typeOf(el: Element): string {
  if (el.matches('h2')) return 'text'
  if (el.matches('.callout, .code, .table-wrap, blockquote, .fig, .gallery')) return 'rise'
  if (el.matches('hr')) return 'draw-x'
  return 'fade'
}

function enhance(): void {
  const box = root.value
  if (!box) return
  box.querySelectorAll<HTMLImageElement>('img[data-color]').forEach((img) => { img.style.backgroundColor = img.dataset.color ?? '' })
  labelTasks(box)
  // a picture that opens the viewer is a control: reachable and operable with the keyboard
  box.querySelectorAll<HTMLImageElement>('.fig img, .gallery__item img').forEach((img) => {
    if (img.closest('a')) return
    img.tabIndex = 0
    img.setAttribute('role', 'button')
    img.setAttribute('aria-label', `查看大图：${img.alt || '图片'}`)
  })
  scrollable()
  if (props.blocks) {
    for (const el of [...box.children] as HTMLElement[]) {
      if (el.hasAttribute('data-fx')) continue
      let type = typeOf(el)
      if (type === 'text' && !splitHeading(el, narrow.value)) type = 'fade'
      el.setAttribute('data-fx', type)
    }
    adopt(box)
  }
}

function scrollable(): void {
  if (root.value) markScrollable(root.value)
}

function pictures(): HTMLImageElement[] {
  return [...(root.value?.querySelectorAll<HTMLImageElement>('.fig img, .gallery__item img') ?? [])]
}

function openPicture(img: HTMLImageElement): void {
  const all = pictures()
  const items: LightboxItem[] = all.map((p) => ({
    src: p.dataset.full || p.currentSrc || p.src,
    alt: p.alt,
    caption: p.closest('figure')?.querySelector('figcaption')?.textContent?.trim() || p.alt,
  }))
  openLightbox(items, all.indexOf(img), img)
}

async function copyCode(button: HTMLElement): Promise<void> {
  const pre = button.closest('.code')?.querySelector('pre')
  if (!pre) return
  const ok = await copyText(pre.innerText)
  const label = button.querySelector('span')
  const old = label?.textContent ?? '复制'
  if (label) label.textContent = ok ? '已复制' : '复制失败'
  button.classList.toggle('is-done', ok)
  window.clearTimeout(copyTimer)
  copyTimer = window.setTimeout(() => { if (label) label.textContent = old === '已复制' || old === '复制失败' ? '复制' : old; button.classList.remove('is-done') }, 1600)
}

function onKey(e: KeyboardEvent): void {
  const img = (e.target as HTMLElement).closest('img')
  if ((e.key === 'Enter' || e.key === ' ') && img && img.closest('.fig, .gallery__item') && !img.closest('a')) { e.preventDefault(); openPicture(img) }
}

function onClick(e: MouseEvent): void {
  const target = e.target as HTMLElement
  const copy = target.closest<HTMLElement>('.code__copy')
  if (copy) { e.preventDefault(); void copyCode(copy); return }
  const img = target.closest('img')
  if (img && img.closest('.fig, .gallery__item') && !img.closest('a')) { e.preventDefault(); openPicture(img); return }
  internalLink(e, router)
}

let ro: ResizeObserver | null = null
onMounted(() => {
  enhance()
  if ('ResizeObserver' in window && root.value) { ro = new ResizeObserver(() => scrollable()); ro.observe(root.value) }
})
watch(() => props.html, async () => {
  if (root.value) release(root.value)
  await nextTick()
  enhance()
})
onBeforeUnmount(() => { window.clearTimeout(copyTimer); ro?.disconnect(); if (root.value) release(root.value) })
defineExpose({ el: root })
</script>

<template>
  <div ref="root" class="prose" :class="articleClass" @click="onClick" @keydown="onKey" v-html="html" />
</template>
