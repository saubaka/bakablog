/* What the page tells the menu thread while a page change is being decided: which entry the visitor is heading for (a click on a bead, a push past the edge that went far
   enough) and how far a push that has not gone far enough has pulled the heart towards its neighbour. Plain values read by the thread's own frame job (layout/ThreadNav.vue):
   they are not reactive, so a push does not re-render the menu. Entries are named by their address because the side menu and the bottom bar are different lists. */
import { ref } from 'vue'
import { wake } from '@/shared/frame'

/** The address of the entry the visitor is heading for, until the page has changed (or the attempt has failed). */
export const pendingUrl = ref<string | null>(null)
let timer = 0

export function setPending(url: string | null): void {
  window.clearTimeout(timer)
  pendingUrl.value = url
  if (url) timer = window.setTimeout(() => { pendingUrl.value = null; wake() }, 6000)   // a navigation that never arrives must not leave the heart somewhere it is not
  wake()
}

let lean: { url: string; amount: number } | null = null
/** Pull the heart a fraction `amount` (0..1) of the way from the current bead to the one at `url`; `null` lets go. */
export function setLean(next: { url: string; amount: number } | null): void {
  lean = next && next.amount > 0.0005 ? next : null
  wake()
}
export const getLean = (): { url: string; amount: number } | null => lean
