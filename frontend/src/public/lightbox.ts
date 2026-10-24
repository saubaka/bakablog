import { shallowRef } from 'vue'

export interface LightboxItem { src: string; alt: string; caption: string }
export const lightbox = shallowRef<{ items: LightboxItem[]; index: number; opener: HTMLElement | null } | null>(null)

export function openLightbox(items: LightboxItem[], index: number, opener: HTMLElement | null = null): void {
  if (!items.length) return
  lightbox.value = { items, index: Math.max(0, Math.min(index, items.length - 1)), opener }
}
export function closeLightbox(): void {
  const cur = lightbox.value
  lightbox.value = null
  cur?.opener?.focus({ preventScroll: true })
}
