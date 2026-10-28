import { nextTick, onBeforeUnmount, onMounted, watch, type Ref } from 'vue'

/* A marker that slides to the item that is current (the category tabs, the month list, the card / list switch).
   The box holds the marker (an element with class "slide") and the items; the current item is found with `pick`. Its place and size are written on the box as
   --x --y --w --h (pixels, relative to the box, so the box must be positioned); CSS decides which of them the marker uses. The box says data-slide="placed", and
   "set" a moment later: the marker moves only then, so a page that opens does not play a slide from the corner. (An attribute, not a class: Vue rewrites a bound class whole.) */
export function useSlider(box: Ref<HTMLElement | null>, pick: string, follow: () => unknown): void {
  let watcher: ResizeObserver | null = null
  let watched: HTMLElement | null = null

  function place(): void {
    const el = box.value
    if (!el) return
    if (el !== watched && 'ResizeObserver' in window) { watcher ??= new ResizeObserver(place); if (watched) watcher.unobserve(watched); watcher.observe(el); watched = el }
    const at = el.querySelector<HTMLElement>(pick)
    if (!at) { delete el.dataset.slide; return }
    el.style.setProperty('--x', `${at.offsetLeft}px`)
    el.style.setProperty('--y', `${at.offsetTop}px`)
    el.style.setProperty('--w', `${at.offsetWidth}px`)
    el.style.setProperty('--h', `${at.offsetHeight}px`)
    if (!el.dataset.slide) {
      el.dataset.slide = 'placed'
      requestAnimationFrame(() => requestAnimationFrame(() => { if (el.dataset.slide) el.dataset.slide = 'set' }))
    }
  }

  onMounted(() => {
    place()
    document.fonts?.ready.then(place).catch(() => undefined)
  })
  watch(follow, () => { void nextTick(place) }, { flush: 'post' })
  onBeforeUnmount(() => watcher?.disconnect())
}
