import type { Directive, DirectiveBinding } from 'vue'
import { register, unregister } from './engine'

export type FxType = 'rise' | 'fade' | 'pop' | 'slide' | 'mask' | 'draw-x' | 'draw-y' | 'spine' | 'drift' | 'text'
export interface FxOptions {
  type: FxType
  /** 0, 1, 2 ... : the element belongs to the page head and enters on its own clock when the page opens, in this order. */
  intro?: number
  /** pop: starting rotation in degrees (default alternates -3 / 3). */
  rot?: number
  /** slide: -1 comes from the left, 1 from the right. */
  dx?: -1 | 1
  /** mask: corner radius of the reveal, e.g. 28 for a large cover. */
  radius?: number
  /** drift: distance in px at the edges of the screen. */
  drift?: number
}
export type FxValue = FxType | FxOptions

const norm = (v: FxValue | undefined): FxOptions => (typeof v === 'string' ? { type: v } : v ?? { type: 'fade' })

function apply(el: HTMLElement, v: FxValue | undefined): void {
  const o = norm(v)
  el.dataset.fx = o.type
  if (o.intro !== undefined) el.dataset.fxIntro = String(o.intro)
  else delete el.dataset.fxIntro
  if (o.rot !== undefined) el.style.setProperty('--fx-rot', String(o.rot))
  if (o.dx !== undefined) el.style.setProperty('--fx-dx', String(o.dx))
  if (o.radius !== undefined) el.style.setProperty('--fx-r', `${o.radius}px`)
  if (o.drift !== undefined) el.style.setProperty('--drift', `${o.drift}px`)
}

/** v-fx="'rise'"  |  v-fx="{ type: 'pop', intro: 2 }".  Sets the data attributes the CSS reads and hands the element to the engine. */
export const vFx: Directive<HTMLElement, FxValue> = {
  mounted(el, binding: DirectiveBinding<FxValue>) {
    apply(el, binding.value)
    register(el)
  },
  updated(el, binding: DirectiveBinding<FxValue>) {
    if (JSON.stringify(binding.value) !== JSON.stringify(binding.oldValue)) apply(el, binding.value)
  },
  unmounted(el) {
    unregister(el)
  },
}
