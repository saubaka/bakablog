import '@/ui/css/index.css'
import { createApp } from 'vue'
import { vFx } from '@/fx/directive'
import * as fx from '@/fx/engine'
import App from './App.vue'
import { applyAppearance } from './appearance'
import { fetchSite } from './data'
import { createAppRouter } from './router'
import { setSite, takeBootData } from './state'

async function start(): Promise<void> {
  const boot = takeBootData()
  const site = boot?.site ?? (await fetchSite())
  setSite(site)
  applyAppearance(site)
  fx.init(site.motion)
  ;(window as unknown as { FX: typeof fx.FX }).FX = fx.FX   // read-only handle for the QA scripts (tests/qa audits sample the numbers)

  const router = createAppRouter(boot)
  const app = createApp(App)
  app.directive('fx', vFx)
  app.config.errorHandler = (err) => { console.error(err) }
  app.use(router)
  await router.isReady()
  app.mount('#app')

  // the first picture of every [data-fx] element is computed in a microtask after mounting; lift the guards behind it
  queueMicrotask(() => {
    fx.reveal()
    document.documentElement.classList.remove('boot')
  })
}

start().catch((err: unknown) => {
  // never leave a blank page: show the server's plain copy of the page
  console.error(err)
  document.documentElement.classList.remove('boot', 'fx-pending')
})
