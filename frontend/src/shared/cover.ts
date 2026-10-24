/* A cover for a post without a picture: a quiet pattern chosen from the title, so the same post always gets the same one.
   Pure CSS (ui/css/components.css: .cv-*), nothing to download. */

const COLORS = ['cv-sky', 'cv-rose', 'cv-mist', 'cv-paper'] as const
const PATTERNS = ['cv-dots', 'cv-stripe', 'cv-grid', 'cv-wave'] as const

/** FNV-1a: small, stable across browsers, good enough to spread titles over 16 combinations. */
export function hash(text: string): number {
  let h = 0x811c9dc5
  for (let i = 0; i < text.length; i += 1) {
    h ^= text.charCodeAt(i)
    h = Math.imul(h, 0x01000193)
  }
  return h >>> 0
}

export function coverClasses(seed: string): string {
  const h = hash(seed)
  const color = COLORS[h % COLORS.length]
  const pattern = PATTERNS[Math.floor(h / COLORS.length) % PATTERNS.length]
  return `${color} ${pattern}`
}
