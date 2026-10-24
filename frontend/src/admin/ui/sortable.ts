import { onBeforeUnmount, ref } from 'vue'

/* Drag to reorder, with a pointer (mouse, touch, pen) or the keyboard (ArrowUp / ArrowDown on the handle).
   The dragged row jumps to the place under the pointer as it crosses its neighbours: no transforms to keep in step with the layout.
   Usage: const sort = useSortable(() => list.value, (next) => (list.value = next)); then on each row  :data-sort-row  and a handle  v-bind="sort.handle(index)". */

export function move<T>(list: T[], from: number, to: number): T[] {
  if (from === to || from < 0 || to < 0 || from >= list.length || to >= list.length) return list
  const next = [...list]
  const [item] = next.splice(from, 1)
  next.splice(to, 0, item as T)
  return next
}

export function useSortable<T>(get: () => T[], set: (next: T[]) => void) {
  const dragging = ref(-1)
  const announce = ref('')
  let rows: HTMLElement[] = []
  let raf = 0
  let lastY = 0
  let scroller = 0

  function rowsOf(handle: HTMLElement): HTMLElement[] {
    const first = handle.closest<HTMLElement>('[data-sort-row]')
    const parent = first?.parentElement
    return parent ? [...parent.querySelectorAll<HTMLElement>(':scope > [data-sort-row]')] : []
  }

  function targetIndex(y: number): number {
    for (let i = 0; i < rows.length; i += 1) {
      const r = (rows[i] as HTMLElement).getBoundingClientRect()
      if (y >= r.top && y <= r.bottom) return i
    }
    return -1
  }

  function place(): void {
    const to = targetIndex(lastY)
    if (to >= 0 && to !== dragging.value) { set(move(get(), dragging.value, to)); dragging.value = to }
  }

  function onMove(e: PointerEvent): void {
    lastY = e.clientY
    if (raf) return
    raf = requestAnimationFrame(() => { raf = 0; place() })
  }

  function autoScroll(): void {
    if (dragging.value < 0) return
    const edge = 70
    if (lastY < edge) window.scrollBy(0, -14)
    else if (lastY > window.innerHeight - edge) window.scrollBy(0, 14)
    scroller = requestAnimationFrame(autoScroll)
  }

  function stop(): void {
    if (raf) { cancelAnimationFrame(raf); raf = 0; if (dragging.value >= 0) place() }   // a quick flick: the last move must not be dropped
    dragging.value = -1
    cancelAnimationFrame(scroller)
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', stop)
    window.removeEventListener('pointercancel', stop)
  }

  function handle(index: number) {
    return {
      'aria-roledescription': '可排序的项',
      onPointerdown: (e: PointerEvent) => {
        if (e.button !== 0) return
        const el = e.currentTarget as HTMLElement
        rows = rowsOf(el)
        dragging.value = index
        lastY = e.clientY
        el.setPointerCapture?.(e.pointerId)
        window.addEventListener('pointermove', onMove)
        window.addEventListener('pointerup', stop)
        window.addEventListener('pointercancel', stop)
        scroller = requestAnimationFrame(autoScroll)
        e.preventDefault()
      },
      onKeydown: (e: KeyboardEvent) => {
        const d = e.key === 'ArrowUp' ? -1 : e.key === 'ArrowDown' ? 1 : 0
        if (!d) return
        e.preventDefault()
        const to = index + d
        if (to < 0 || to >= get().length) return
        set(move(get(), index, to))
        announce.value = `已移到第 ${to + 1} 位，共 ${get().length} 项`
        requestAnimationFrame(() => {
          const row = (e.target as HTMLElement).closest('[data-sort-row]')?.parentElement?.querySelectorAll<HTMLElement>(':scope > [data-sort-row]')[to]
          row?.querySelector<HTMLElement>('[data-sort-handle]')?.focus()
        })
      },
      'data-sort-handle': '',
    }
  }

  onBeforeUnmount(stop)
  return { dragging, announce, handle }
}
