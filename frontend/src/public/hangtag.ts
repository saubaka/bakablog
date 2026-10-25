/* The hanging tag: the reading progress as a small tag that hangs on a thread at the right edge of the screen, level with the topmost pin of the menu on the left.
   Only the numbers live here (pure, tested); the springs and the drawing are in layout/ProgressTag.vue. */

/** How far above the point it rides on (px) the tag waits while it is away: far enough to be out of the screen. */
export const AWAY = 80
/** The tag hangs this far (px) below the point of the line it rides on: the lowest the point may go is this far above the lowest free place. */
export const HANG_BELOW = 52
/** Where the thread starts when there is no menu on the left (phones, tablets). */
export const FALLBACK_TOP = 28
/** On small screens the tag only hangs out while the page is being scrolled, and for this long (ms) afterwards. */
export const IDLE_MS = 1400
/** A page that scrolls less than this (px) has no tag: there is nothing to read down to. */
export const MIN_ROOM = 120

export interface Geometry {
  /** Height (px from the top of the screen) of the point of the line where the page is at its start. */
  top: number
  /** Length (px) of the line: the way the point travels between the start and the end of the page. */
  len: number
}

const clamp = (x: number, lo: number, hi: number): number => Math.min(Math.max(x, lo), hi)
export const clamp01 = (x: number): number => clamp(x, 0, 1)

/** `pinMid`: the middle of the menu's topmost pin (null when there is no menu on the left). `floor`: the lowest y that is free (the bottom of the screen, the top of the
    bottom bar, the top of the contents button). */
export function geometry(pinMid: number | null, floor: number): Geometry {
  const top = pinMid ?? FALLBACK_TOP
  return { top, len: Math.max(floor - HANG_BELOW - top, 120) }
}

/** The height of the point the tag hangs from. `p`: how much has been read (0..1). `drop`: 0 = hanging in place, 1 = away above the screen, below 0 = bounced past. */
export function tagY(g: Geometry, p: number, drop: number): number {
  const y = g.top + clamp01(p) * g.len
  return y - drop * (y + AWAY)
}

/** The angle (degrees) the tag is pulled to by the speed of the reading progress (units of the whole page per second): it lags behind the thread and swings back. */
export const swingTarget = (speed: number): number => clamp(-speed * 34, -18, 18)

export const percent = (p: number): string => `${Math.round(clamp01(p) * 100)}%`

export interface Want { armed: boolean; room: number; narrow: boolean; sinceScroll: number }
/** Should the tag hang out now? Not on a page that does not scroll, not before the page has arrived, and on small screens only while it is being scrolled. */
export function wantShown(w: Want): boolean {
  return w.armed && w.room > MIN_ROOM && (!w.narrow || w.sinceScroll < IDLE_MS)
}
