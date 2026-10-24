/* Page changes and scrolling.
   A page swap is a cross-fade (the old page leaves, the new one is mounted and enters). Restoring a scroll position has to wait
   until the new page exists, otherwise the browser clamps the position to the height of the page that is about to disappear.
   The new page must also be AT its start position (the top, or the place Back / Forward saved) before the motion engine places its
   elements: the engine decides each element's first picture and whether the page head plays its entrance from the scroll position
   it finds. The app therefore scrolls the moment the new page is inserted (`applyPendingScroll`, called from the transition's
   `enter` hook), not after the cross-fade like the router's own scroll step. */

let swapped = false
let pending: { left: number; top: number } | null = null

/** Where the page that is about to be inserted must start. Set by the router for every navigation that swaps the page. */
export function setPendingScroll(at: { left: number; top: number } | null): void {
  pending = at
}

/** Put the scroll position where the new page starts. The page is in the document by now, so the position cannot be clamped. */
export function applyPendingScroll(): void {
  const at = pending
  pending = null
  if (at) window.scrollTo({ left: at.left, top: at.top, behavior: 'instant' })
}
let resolveReady: (() => void) | null = null
let ready: Promise<void> | null = null

/** Get or set: did the last navigation replace the page component? */
export function pageSwapped(value?: boolean): boolean {
  if (value !== undefined) {
    swapped = value
    if (value && !ready) ready = new Promise<void>((resolve) => { resolveReady = resolve })
    if (!value) notifyPageReady()
  }
  return swapped
}

/** Resolves when the new page has been mounted; gives up after 700 ms so scrolling never waits for a stuck animation. */
export function whenPageReady(): Promise<void> {
  const p = ready
  if (!p) return Promise.resolve()
  return Promise.race([p, new Promise<void>((resolve) => setTimeout(resolve, 700))])
}

export function notifyPageReady(): void {
  swapped = false
  resolveReady?.()
  ready = null
  resolveReady = null
}

/** After a navigation: the keyboard and screen readers continue at the page's title, not at the link that was clicked.
    The heading is focusable (tabindex -1) but never draws a focus ring (ui/css/base.css). */
export function focusPageTitle(): void {
  const target = document.querySelector<HTMLElement>('main h1') ?? document.getElementById('main')
  if (!target) return
  if (!target.hasAttribute('tabindex')) target.setAttribute('tabindex', '-1')
  target.focus({ preventScroll: true })
}
