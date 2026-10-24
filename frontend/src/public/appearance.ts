import type { SiteInfo } from '@/shared/types'

/** Theme, code theme and decoration switches on <html>. boot.js does the same before the first paint (from the server's inlined data);
    this runs when that data was not there (the dev server) and whenever the settings change. Keep the two in step (tests/boot.test.ts). */
export function applyAppearance(site: SiteInfo, root: HTMLElement = document.documentElement): void {
  if (site.theme && site.theme !== 'default') root.setAttribute('data-theme', site.theme)
  else root.removeAttribute('data-theme')
  if (site.code_theme) root.setAttribute('data-code-theme', site.code_theme)
  root.classList.toggle('no-tape', site.decor.tape === false)
  root.classList.toggle('no-doodles', site.decor.doodles === false)
  if (site.language) root.lang = site.language
}
