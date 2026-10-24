import { ref } from 'vue'

/* Overlays that several parts of the page open (header, bottom bar, 404 page, keyboard shortcuts). */
export const searchOpen = ref(false)
export const moreOpen = ref(false)

export const openSearch = (): void => { moreOpen.value = false; searchOpen.value = true }
export const closeSearch = (): void => { searchOpen.value = false }
export const openMore = (): void => { moreOpen.value = true }
export const closeMore = (): void => { moreOpen.value = false }

export const reducedMotion = (): boolean => typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches

export function scrollToTop(): void {
  window.scrollTo({ top: 0, behavior: reducedMotion() ? 'auto' : 'smooth' })
}
