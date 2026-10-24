/* Words for what the server records: audit actions, post statuses, todo kinds. One place, so a log line and a button say the same thing. */
const ACTIONS: Record<string, string> = {
  'auth.login': '登录', 'auth.logout': '退出登录', 'auth.setup': '完成首次安装', 'auth.password_changed': '修改了密码', 'auth.username_changed': '修改了用户名',
  'auth.totp_enabled': '开启二次验证', 'auth.totp_disabled': '关闭二次验证', 'auth.recovery_code_used': '使用了一次性恢复码',
  'auth.session_revoked': '让一个登录会话下线', 'auth.sessions_revoked': '让其他登录会话下线',
  'post.create': '新建文章', 'post.update': '修改文章', 'post.trash': '把文章移入回收站', 'post.restore': '恢复文章', 'post.purge': '永久删除文章',
  'post.batch': '批量处理文章', 'post.revision_restore': '恢复文章的历史版本',
  'moment.create': '发布动态', 'moment.update': '修改动态', 'moment.trash': '把动态移入回收站', 'moment.restore': '恢复动态', 'moment.purge': '永久删除动态', 'moment.batch': '批量处理动态',
  'page.create': '新建页面', 'page.update': '修改页面', 'page.trash': '把页面移入回收站', 'page.restore': '恢复页面', 'page.purge': '永久删除页面', 'page.revision_restore': '恢复页面的历史版本',
  'media.upload': '上传图片', 'media.update': '修改图片信息', 'media.replace': '替换图片文件', 'media.trash': '把图片移入回收站', 'media.restore': '恢复图片', 'media.purge': '永久删除图片',
  'category.create': '新建分类', 'category.update': '修改分类', 'category.delete': '删除分类', 'category.reorder': '调整分类顺序',
  'tag.create': '新建标签', 'tag.update': '修改标签', 'tag.delete': '删除标签', 'tag.merge': '合并标签', 'tag.cleanup': '清理没用的标签',
  'series.create': '新建系列', 'series.update': '修改系列', 'series.delete': '删除系列', 'series.order': '调整系列里的文章顺序',
  'settings.update': '修改设置', 'settings.reset': '恢复默认设置', 'home.update': '保存首页配置', 'home.reset': '恢复默认首页',
  'nav.update': '保存导航', 'nav.reset': '恢复默认导航', 'redirect.create': '新建重定向', 'redirect.update': '修改重定向', 'redirect.delete': '删除重定向',
  'system.backup': '立即备份', 'system.backup_delete': '删除备份', 'system.restore': '从备份恢复', 'system.job': '运行维护任务', 'system.export': '导出整站', 'system.import': '导入内容', 'system.backup_download': '下载备份',
  'trash.empty': '清空回收站',
}

export function actionLabel(action: string): string {
  return ACTIONS[action] ?? action
}

export const STATUS_LABEL: Record<string, string> = { draft: '草稿', published: '已发布', scheduled: '定时', unlisted: '仅链接可见', private: '私密', trashed: '回收站' }
export const VISIBILITY_LABEL: Record<string, string> = { public: '公开', unlisted: '仅链接可见', private: '私密' }
export const TARGET_LABEL: Record<string, string> = { post: '文章', moment: '动态', page: '页面', media: '图片', category: '分类', tag: '标签', series: '系列', settings: '设置', home: '首页', nav: '导航', redirect: '重定向', backup: '备份', auth: '账号', system: '系统' }

export function todoText(t: { kind: string; title?: string; days?: number; at?: string; count?: number }): string {
  switch (t.kind) {
    case 'stale_draft': return `「${t.title ?? ''}」已经 ${t.days ?? 7} 天没动过，要发布还是继续写？`
    case 'scheduled_soon': return `「${t.title ?? ''}」即将自动发布`
    case 'missing_cover': return `「${t.title ?? ''}」还没有封面`
    case 'missing_summary': return `「${t.title ?? ''}」没有摘要（现在是自动截取的）`
    case 'image_no_alt': return `有 ${t.count ?? 0} 张图片没有替代文字`
    default: return t.title ?? t.kind
  }
}
