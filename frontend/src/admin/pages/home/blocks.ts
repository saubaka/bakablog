/* What the home page is made of: the eight modules, their names, and a sensible starting value for each (the server validates the real limits). */
export interface BlockMeta { type: string; name: string; icon: string; help: string }

export const BLOCKS: BlockMeta[] = [
  { type: 'hero', name: '首屏名片', icon: 'smile', help: '大标题、简介、按钮和拍立得照片。' },
  { type: 'notice', name: '公告条', icon: 'a-bell', help: '一行字，可以设置只在某段时间显示。' },
  { type: 'featured', name: '精选文章', icon: 'sparkle', help: '自动挑选，或者自己指定最多 6 篇。' },
  { type: 'latest_posts', name: '最近的文章', icon: 'book', help: '最新发布的文章。' },
  { type: 'latest_moments', name: '最近的动态', icon: 'chat', help: '最新的几条动态。' },
  { type: 'shelf', name: '书架', icon: 'grid', help: '分类和常用标签。' },
  { type: 'about', name: '关于我', icon: 'heart', help: '头像、简介和社交链接在“外观与站点”里设置。' },
  { type: 'now', name: '近况', icon: 'pin', help: '放在“关于我”旁边的小便签。' },
]
export const META = Object.fromEntries(BLOCKS.map((b) => [b.type, b])) as Record<string, BlockMeta>

export const DOODLES: { value: string; label: string }[] = [
  { value: 'star', label: '星星' }, { value: 'heart', label: '爱心' }, { value: 'sparkle', label: '闪光' },
  { value: 'flower', label: '小花' }, { value: 'paw', label: '脚印' }, { value: 'wave', label: '波浪' }, { value: 'loop', label: '线圈' },
]

export function defaultConfig(type: string): Record<string, unknown> {
  switch (type) {
    case 'hero': return { note: '', title_lines: ['你好，'], intro: '', buttons: [], polaroid: { media_id: null, caption: '', bubble: '' }, doodles: [] }
    case 'notice': return { text: '', starts_at: null, ends_at: null }
    case 'featured': return { title: '精选', mode: 'auto', post_ids: [], count: 3 }
    case 'latest_posts': return { title: '最近的文章', intro: '', count: 6, layout: 'mixed' }
    case 'latest_moments': return { title: '最近的动态', intro: '', count: 3 }
    case 'shelf': return { title: '书架', intro: '', tag_count: 14 }
    case 'about': return { title: '关于我', intro: '', text: [] }
    case 'now': return { title: '近况', items: [] }
    default: return {}
  }
}
