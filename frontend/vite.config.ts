import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'
import { defineConfig, type Plugin } from 'vitest/config'

const here = (p: string) => fileURLToPath(new URL(p, import.meta.url))
const API = process.env.BLOG_API ?? 'http://127.0.0.1:5300'

/* Paths the Flask server answers itself; everything else in dev is the public page shell (or the admin shell under /admin). */
const SERVER_PREFIXES = ['/api/', '/media/', '/feed/', '/sitemap.xml', '/robots.txt']

/** Dev server: any address without a file extension gets public.html (the history-mode router takes over).
    The Flask server writes <head> and the first-screen data into the real shell; in dev only the icon is filled in. */
function pageFallback(): Plugin {
  return {
    name: 'bb-page-fallback',
    apply: 'serve',
    transformIndexHtml: (html) => html.replace('<!--bb:head-->', '<link rel="icon" href="/favicon.svg">'),
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        const url = req.url ?? '/'
        const path = url.split('?')[0] ?? '/'
        const wantsPage = req.method === 'GET' && !path.includes('.') && !SERVER_PREFIXES.some((p) => path.startsWith(p)) && !path.startsWith('/@') && !path.startsWith('/src/') && !path.startsWith('/node_modules/')
        const query = url.includes('?') ? url.slice(url.indexOf('?')) : ''
        if (wantsPage) req.url = `${path === '/admin/preview-frame' ? '/preview.html' : path === '/admin' || path.startsWith('/admin/') ? '/admin.html' : '/public.html'}${query}`
        next()
      })
    },
  }
}

export default defineConfig({
  plugins: [vue(), pageFallback()],
  resolve: { alias: { '@': here('./src'), '@samples': here('../docs/api-samples') } },
  appType: 'mpa',
  server: {
    port: 5173,
    strictPort: true,
    fs: { allow: [here('.'), here('../docs')] },
    proxy: Object.fromEntries(SERVER_PREFIXES.map((p) => [p, { target: API, changeOrigin: false }])),
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    emptyOutDir: true,
    target: ['es2020', 'chrome100', 'safari15.4', 'firefox100'],
    cssTarget: ['chrome100', 'safari15.4', 'firefox100'],
    cssCodeSplit: true,   // the admin has its own stylesheet; the public page loads none of it
    sourcemap: false,
    modulePreload: { polyfill: false },
    chunkSizeWarningLimit: 220,
    rollupOptions: {
      input: { public: here('./public.html'), admin: here('./admin.html'), preview: here('./preview.html') },
      output: {
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
        manualChunks: (id) => {
          if (/node_modules\/(vue|@vue|vue-router)\//.test(id)) return 'vendor'
          // sprite, icons, motion engine, API types and helpers are used by every page; stylesheets are not put in here: each page gets only its own
          if (/\/src\/(ui|shared|fx)\//.test(id) && !id.endsWith('.css')) return 'common'
          return undefined
        },
      },
    },
  },
  test: {
    environment: 'happy-dom',
    include: ['tests/**/*.test.ts'],
    css: false,
    restoreMocks: true,
  },
})
