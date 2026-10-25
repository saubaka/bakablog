/* The admin's navigation: groups of pages (docs/PLAN.md 5.1). One list drives the sidebar, the phone drawer and the command palette. */
export interface NavEntry { to: string; label: string; icon: string; keywords?: string }
export interface NavGroup { id: string; label: string; items: NavEntry[] }

export const NAV: NavGroup[] = [
  { id: 'overview', label: '概览', items: [{ to: '/', label: '仪表盘', icon: 'a-dashboard', keywords: 'dashboard home 首页 概览' }] },
  { id: 'content', label: '内容', items: [
    { to: '/posts', label: '文章', icon: 'book', keywords: 'posts articles 博客' },
    { to: '/moments', label: '动态', icon: 'chat', keywords: 'moments 碎碎念' },
    { to: '/pages', label: '页面', icon: 'smile', keywords: 'pages 关于' },
    { to: '/media', label: '媒体库', icon: 'image', keywords: 'media pictures 图片' },
    { to: '/trash', label: '回收站', icon: 'a-trash', keywords: 'trash 删除' },
  ] },
  { id: 'organize', label: '整理', items: [
    { to: '/categories', label: '分类', icon: 'folder', keywords: 'categories' },
    { to: '/tags', label: '标签', icon: 'tag', keywords: 'tags' },
    { to: '/series', label: '系列', icon: 'list', keywords: 'series 连载' },
  ] },
  { id: 'site', label: '站点', items: [
    { to: '/home', label: '首页配置', icon: 'home', keywords: 'home blocks 模块' },
    { to: '/navigation', label: '导航与页脚', icon: 'a-menu', keywords: 'navigation nav footer 页脚' },
    { to: '/appearance', label: '外观', icon: 'sparkle', keywords: 'appearance theme 主题 站点信息' },
    { to: '/seo', label: 'SEO', icon: 'search', keywords: 'seo sitemap robots redirects 重定向 搜索引擎' },
  ] },
  { id: 'data', label: '数据', items: [{ to: '/stats', label: '访问统计', icon: 'a-activity', keywords: 'stats visits 统计' }] },
  { id: 'system', label: '系统', items: [
    { to: '/account', label: '账号与安全', icon: 'a-shield', keywords: 'account password totp sessions 密码' },
    { to: '/backups', label: '备份与导入导出', icon: 'a-database', keywords: 'backup restore export import 备份' },
    { to: '/logs', label: '日志', icon: 'clock', keywords: 'audit logs 审计 登录' },
    { to: '/system', label: '系统状态', icon: 'a-settings', keywords: 'system status jobs 任务' },
  ] },
]

export const ALL_ENTRIES: NavEntry[] = NAV.flatMap((g) => g.items)

/** The entry a path belongs to ("/posts/12" -> "/posts"), so the sidebar highlights the right place on detail pages. */
export function entryFor(path: string): NavEntry | null {
  if (path === '/') return ALL_ENTRIES.find((e) => e.to === '/') ?? null
  let best: NavEntry | null = null
  for (const e of ALL_ENTRIES) {
    if (e.to !== '/' && (path === e.to || path.startsWith(`${e.to}/`)) && (!best || e.to.length > best.to.length)) best = e
  }
  return best
}

/** The phone's bottom bar: the four places used most, and "more" for the rest. */
export const TABBAR: NavEntry[] = [
  { to: '/', label: '概览', icon: 'a-dashboard' },
  { to: '/posts', label: '文章', icon: 'book' },
  { to: '/moments', label: '动态', icon: 'chat' },
  { to: '/media', label: '媒体', icon: 'image' },
]
