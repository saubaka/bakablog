import '@/admin/css/index.css'
import { createApp } from 'vue'
import * as fx from '@/fx/engine'
import { setSite } from '@/public/state'
import { applyAppearance } from '@/public/appearance'
import { fetchSite } from '@/public/data'
import App from './App.vue'
import { configureClient } from './api/client'
import { auth, bootstrap, clear, loadMe } from './auth'
import { createAdminRouter } from './router'

async function start(): Promise<void> {
  const router = createAdminRouter()
  configureClient({
    onUnauthorized: () => {
      clear()
      if (!router.currentRoute.value.meta.open) void router.replace({ name: 'login', query: { next: router.currentRoute.value.fullPath } })
    },
    refreshCsrf: loadMe,
  })
  fx.init('off')                        // the admin has no scroll motion; shared components that use v-fx simply sit still
  // the site's own theme also applies here; the admin works without it
  fetchSite().then((s) => { setSite(s); applyAppearance(s) }).catch(() => undefined)
  await bootstrap()
  const app = createApp(App)
  app.directive('fx', { mounted: () => undefined })
  app.config.errorHandler = (err) => { console.error(err) }
  app.use(router)
  await router.isReady()
  // the guards ran before the first status answer; run them again now that we know who is here
  const here = router.currentRoute.value
  if (auth.setupRequired && here.name !== 'setup') await router.replace({ name: 'setup' })
  else if (!here.meta.open && !auth.user) await router.replace({ name: 'login', query: here.fullPath !== '/' ? { next: here.fullPath } : {} })
  app.mount('#app')
}

start().catch((err: unknown) => {
  console.error(err)
  const el = document.getElementById('app')
  if (el) el.textContent = '后台没有加载成功，请刷新页面再试。'
})
