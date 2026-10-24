import type { Router } from 'vue-router'
import { isServerPath } from './router'

/** Click handler for links inside HTML we did not render with Vue (article text, moment text): an internal link navigates inside
    the app; anything else (other sites, feeds, the admin, new-tab clicks, downloads) is left to the browser. Links stay real links. */
export function internalLink(e: MouseEvent, router: Router): boolean {
  const a = (e.target as HTMLElement).closest('a')
  if (!a || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return false
  if ((a.target && a.target !== '_self') || a.hasAttribute('download')) return false
  const href = a.getAttribute('href') ?? ''
  if (!href) return false
  const url = new URL(a.href, location.href)
  if (url.origin !== location.origin || isServerPath(url.pathname)) return false
  e.preventDefault()
  void router.push({ path: url.pathname, query: Object.fromEntries(url.searchParams), hash: url.hash })
  return true
}
