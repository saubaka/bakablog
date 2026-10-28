import type { NavItem } from '@/shared/types'
import { site } from './state'
import { TABLET } from './viewport'

/** The menu that is on the screen now: the thread on the left edge, or the bar along the bottom on phones and tablets. */
export const activeMenu = (): NavItem[] => (window.matchMedia(`(max-width: ${TABLET}px)`).matches ? site.value.nav.mobile : site.value.nav.top)
