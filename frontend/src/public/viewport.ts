import { computed, readonly, ref } from 'vue'

/* Breakpoints shared by scripts and CSS (ui/css/layout.css and pages.css use the same numbers). */
export const PHONE = 760
export const GRID2 = 1024
export const TABLET = 1100

const narrow = ref(false)
const twoCols = ref(false)
const tablet = ref(false)
let started = false

function start(): void {
  if (started || typeof matchMedia !== 'function') return
  started = true
  const watch = (query: string, target: typeof narrow) => {
    const mq = matchMedia(query)
    target.value = mq.matches
    mq.addEventListener('change', (e) => { target.value = e.matches })
  }
  watch(`(max-width: ${PHONE}px)`, narrow)
  watch(`(max-width: ${GRID2}px)`, twoCols)
  watch(`(max-width: ${TABLET}px)`, tablet)
}

/** Reactive breakpoints: narrow = phone layout (bottom bar), tablet = no sticky side column,
    cols = how many cards fit in a row of the grid (3 wide, 2 on a tablet, 1 on a phone). */
export function useViewport() {
  start()
  const cols = computed<1 | 2 | 3>(() => (narrow.value ? 1 : twoCols.value ? 2 : 3))
  return { narrow: readonly(narrow), tablet: readonly(tablet), cols }
}
