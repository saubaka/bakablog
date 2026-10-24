import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { auth } from './auth'

declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    /** Reachable without signing in (login, first-run setup). */
    open?: boolean
  }
}

const page = (name: string) => () => import(`./pages/${name}.vue`)

export const routes: RouteRecordRaw[] = [
  { path: '/login', name: 'login', component: page('Login'), meta: { open: true, title: '登录' } },
  { path: '/setup', name: 'setup', component: page('Setup'), meta: { open: true, title: '首次安装' } },
  { path: '/', name: 'dashboard', component: page('Dashboard'), meta: { title: '仪表盘' } },
  { path: '/posts', name: 'posts', component: page('PostList'), meta: { title: '文章' } },
  { path: '/posts/new', name: 'post-new', component: page('PostEdit'), meta: { title: '写文章' } },
  { path: '/posts/:id(\\d+)', name: 'post-edit', component: page('PostEdit'), meta: { title: '编辑文章' } },
  { path: '/moments', name: 'moments', component: page('Moments'), meta: { title: '动态' } },
  { path: '/pages', name: 'pages', component: page('PageList'), meta: { title: '页面' } },
  { path: '/pages/new', name: 'page-new', component: page('PageEdit'), meta: { title: '新建页面' } },
  { path: '/pages/:id(\\d+)', name: 'page-edit', component: page('PageEdit'), meta: { title: '编辑页面' } },
  { path: '/media', name: 'media', component: page('Media'), meta: { title: '媒体库' } },
  { path: '/trash', name: 'trash', component: page('Trash'), meta: { title: '回收站' } },
  { path: '/categories', name: 'categories', component: page('Categories'), meta: { title: '分类' } },
  { path: '/tags', name: 'tags', component: page('Tags'), meta: { title: '标签' } },
  { path: '/series', name: 'series', component: page('SeriesPage'), meta: { title: '系列' } },
  { path: '/home', name: 'home', component: page('HomeConfig'), meta: { title: '首页配置' } },
  { path: '/navigation', name: 'navigation', component: page('Navigation'), meta: { title: '导航与页脚' } },
  { path: '/appearance', name: 'appearance', component: page('Appearance'), meta: { title: '外观' } },
  { path: '/seo', name: 'seo', component: page('Seo'), meta: { title: 'SEO 与订阅' } },
  { path: '/stats', name: 'stats', component: page('Stats'), meta: { title: '访问统计' } },
  { path: '/account', name: 'account', component: page('Account'), meta: { title: '账号与安全' } },
  { path: '/backups', name: 'backups', component: page('Backups'), meta: { title: '备份与导入导出' } },
  { path: '/logs', name: 'logs', component: page('Logs'), meta: { title: '日志' } },
  { path: '/system', name: 'system', component: page('System'), meta: { title: '系统状态' } },
  { path: '/:rest(.*)*', name: 'not-found', component: page('NotFound'), meta: { title: '找不到这一页' } },
]

export function createAdminRouter() {
  const router = createRouter({
    history: createWebHistory('/admin'),
    routes,
    scrollBehavior: (_to, _from, saved) => saved ?? { top: 0 },
  })

  router.beforeEach((to) => {
    if (!auth.ready) return true
    if (auth.setupRequired && to.name !== 'setup') return { name: 'setup' }
    if (!auth.setupRequired && to.name === 'setup') return { name: auth.user ? 'dashboard' : 'login' }
    if (!to.meta.open && !auth.user) return { name: 'login', query: to.fullPath !== '/' ? { next: to.fullPath } : {} }
    if (to.name === 'login' && auth.user) return { name: 'dashboard' }
    return true
  })

  router.afterEach((to) => {
    document.title = `${to.meta.title ?? '管理后台'} · 管理后台`
  })

  return router
}
