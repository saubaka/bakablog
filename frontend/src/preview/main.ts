import '@/ui/css/index.css'
import { createApp } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { vFx } from '@/fx/directive'
import * as fx from '@/fx/engine'
import { applyAppearance } from '@/public/appearance'
import { setPage, setSite } from '@/public/state'
import PreviewApp from './PreviewApp.vue'
import type { HomeBlock, SiteInfo } from '@/shared/types'
import { isPreviewMessage, type PreviewReady } from './protocol'

/* The page inside the admin's "preview" frames. It never talks to the API about the site: the admin sends the (unsaved) settings and
   this page draws them with the real public components, at the width of the frame. Nothing here can be clicked. */
const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:pathMatch(.*)*', component: { render: () => null } }] })

function show(site: SiteInfo, home: HomeBlock[]): void {
  setSite(site)
  applyAppearance(site)
  setPage({ kind: 'home', status: 200, data: { blocks: home, site_version: site.site_version } })
}

window.addEventListener('message', (e: MessageEvent) => {
  if (e.origin !== window.location.origin || e.source !== window.parent || !isPreviewMessage(e.data)) return
  show(e.data.site, e.data.home)
})

// links and buttons do nothing in a preview
document.addEventListener('click', (e) => { if ((e.target as Element | null)?.closest('a, button, summary')) e.preventDefault() }, true)
document.addEventListener('submit', (e) => e.preventDefault(), true)

fx.init('off')
const app = createApp(PreviewApp)
app.directive('fx', vFx)
app.use(router)
void router.replace('/').then(() => {
  app.mount('#app')
  document.getElementById('app')?.setAttribute('inert', '')   // nothing in a preview can be focused or clicked; the page itself still scrolls
  const ready: PreviewReady = { type: 'bb-preview-ready' }
  window.parent.postMessage(ready, window.location.origin)
})
