/* Small helpers for motion that does not follow the scroll position: a list that is swapped, a marker that slides, a menu that opens. The scroll motion itself lives in src/fx. */

/** Is the page's motion on? The visitor's "off" choice and the system's "reduce motion" both put `fx-off` on <html> (fx/engine.ts); then every change is simply there. */
export const motionOn = (): boolean => typeof document !== 'undefined' && !document.documentElement.classList.contains('fx-off')

/** Which way a change reads: "next" moves the content in from the right (a later page, a newer month, the list view), "prev" from the left, "none" is a plain fade. */
export type Dir = 'next' | 'prev' | 'none'

/** The direction of going from one value to another (numbers or strings that sort the same way). */
export function dirOf<T extends number | string>(to: T, from: T): Dir {
  return to === from ? 'none' : to > from ? 'next' : 'prev'
}
