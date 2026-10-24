import { onBeforeUnmount, onMounted, ref, type Ref } from 'vue'
import { onFrame } from '@/shared/frame'

/** Which heading of the article is being read: the last one whose top edge has passed the sticky-header line.
    The headings' places in the document are measured when the layout changes (resize, content growing), not on every frame: a scroll only compares numbers. */
export function useActiveHeading(ids: () => string[], line = 140): { active: Ref<number> } {
  const active = ref(0)
  let tops: number[] = []
  let dirty = true
  let stop: (() => void) | null = null
  let observer: ResizeObserver | null = null
  const measure = (): void => {
    tops = ids().map((id) => { const el = document.getElementById(id); return el ? el.getBoundingClientRect().top + window.scrollY : Number.POSITIVE_INFINITY })
    dirty = false
  }
  const markDirty = (): void => { dirty = true }
  onMounted(() => {
    stop = onFrame(() => {
      if (dirty) measure()
      const sy = window.scrollY
      let idx = 0
      tops.forEach((t, i) => { if (t - sy <= line) idx = i })
      return () => { if (active.value !== idx) active.value = idx }
    })
    window.addEventListener('resize', markDirty, { passive: true })
    if ('ResizeObserver' in window) { observer = new ResizeObserver(markDirty); observer.observe(document.body) }
  })
  onBeforeUnmount(() => { stop?.(); window.removeEventListener('resize', markDirty); observer?.disconnect() })
  return { active }
}
