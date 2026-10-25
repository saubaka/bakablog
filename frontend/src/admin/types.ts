/* Shapes of the admin API (docs/api-samples/admin/*.json). Public shapes (posts, media, moments ...) come from shared/types. */
import type { Category, Media, Moment, PostCard, SeriesRef, Tag } from '@/shared/types'

export interface ListPage<T> { items: T[]; total: number; page: number; per: number; pages: number }

/* ---- account ---- */
export interface AdminUser { id: number; username: string; role: string; totp_enabled: boolean; created_at: string; last_login_at: string | null }
export interface AdminSession { id: number; device: string; ip_prefix: string; created_at: string; last_seen_at: string; expires_at: string; current: boolean }
export interface MeResponse { user: AdminUser; csrf_token: string; session: AdminSession }
export interface AuthStatus { setup_required: boolean; authenticated: boolean }
export interface LoginRecord { at: string; success: boolean; reason: string; ip_prefix: string; user_agent: string }

/* ---- posts ---- */
export type PostStatus = 'draft' | 'published' | 'unlisted' | 'private'
export type CardStyle = 'auto' | 'cover' | 'side' | 'note' | 'quote'
export interface AdminCategory extends Category { count: number; public_count: number; sort_order: number; show_on_shelf: boolean }
export interface AdminTag extends Tag { description: string; post_count: number; moment_count: number; count: number }
export interface AdminSeries { id: number; slug: string; title: string; description: string; status: 'ongoing' | 'finished'; cover: Media | null; url: string; count: number; sort_order: number }
export interface AdminPostCard extends Omit<PostCard, 'category' | 'series'> {
  category: (Category & { sort_order?: number; show_on_shelf?: boolean }) | null
  series: SeriesRef | null
  status: PostStatus
  view_count: number
  created_at: string
  deleted_at: string | null
  scheduled: boolean
  summary_auto: boolean
  category_id: number | null
  series_id: number | null
  series_order: number | null
  preview_path: string
}
export interface PostCounts { all: number; draft: number; published: number; scheduled: number; unlisted: number; private: number; trashed: number }
export interface PostList extends ListPage<AdminPostCard> { counts: PostCounts }
export interface AutosaveSnapshot { title?: string; summary?: string; content_md?: string; tags?: string[] }
export interface AdminPost extends AdminPostCard {
  content_md: string
  show_toc: boolean
  show_reading_time: boolean
  show_author_card: boolean
  seo: { title: string; description: string; image: Media | null; canonical_url: string }
  toc: { id: string; text: string; level: number }[]
  series_info: AdminSeries | null
  autosave: { saved_at: string; snapshot: AutosaveSnapshot } | null
}
export interface PostInput {
  title?: string; slug?: string; summary?: string; content_md?: string; status?: PostStatus; published_at?: string | null
  category_id?: number | null; tags?: string[]; series_id?: number | null; series_order?: number | null
  cover_media_id?: number | null; cover_alt?: string; cover_focus_x?: number; cover_focus_y?: number
  pinned?: boolean; featured?: boolean; card_style?: CardStyle
  show_toc?: boolean; show_reading_time?: boolean; show_author_card?: boolean
  seo_title?: string; seo_description?: string; seo_image_media_id?: number | null; canonical_url?: string
  expected_updated_at?: string
}
export interface Revision { id: number; created_at: string; title: string; length: number }
export interface RevisionDetail { id: number; created_at: string; snapshot: Record<string, unknown> & { title?: string; content_md?: string } }

/* ---- moments ---- */
export type Visibility = 'public' | 'unlisted' | 'private'
export interface AdminMedia extends Media {
  hash: string; filename: string; kind: 'image' | 'icon'; mime: string; bytes: number; orig_width: number; orig_height: number
  created_at: string; updated_at: string; deleted_at: string | null; usage_count: number
}
export interface AdminMoment extends Omit<Moment, 'media'> {
  visibility: Visibility; markdown: string; updated_at: string; deleted_at: string | null; view_count: number; created_at: string; scheduled: boolean
  media: (Media & { alt_override?: string })[]
}
export interface MomentList extends ListPage<AdminMoment> { counts: { all: number; trashed: number } }
export interface LinkPreview { url: string; title: string; description: string; domain: string; site_name: string; icon_media_id: number | null; icon: Media | null }
export interface MomentInput {
  text?: string; mood?: string | null; tags?: string[]; auto_tags?: boolean; media?: { media_id: number; alt: string }[]
  link_card?: { url: string; title: string; description: string; icon_media_id?: number | null } | null
  pinned?: boolean; visibility?: Visibility; published_at?: string | null
}

/* ---- media ---- */
export interface MediaUsage { type: string; id: number; title: string; url?: string; admin_url?: string }

/* ---- pages ---- */
export interface AdminPage {
  id: number; slug: string; url: string; title: string; html: string; toc: { id: string; text: string; level: number }[]; template: 'plain' | 'wide' | 'sidebar'
  updated_at: string; status: PostStatus; content_md: string; in_nav: boolean; in_footer: boolean; seo: { title: string; description: string; image: Media | null }
  created_at: string; deleted_at: string | null
}

/* ---- site ---- */
export interface Vocab {
  themes: string[]; motion: string[]; code_themes: string[]; doodles: string[]; icons: string[]; moods: Record<string, string>; tag_colors: string[]
  nav_regions: string[]; nav_kinds: string[]; nav_actions: string[]; routes: string[]; home_block_types: string[]; mobile_nav_max: number
  post_statuses: string[]; card_styles: string[]; page_templates: string[]
}
export interface SettingsGroups {
  site: { name: string; name_en: string; tagline: string; description: string; language: string; timezone: string; logo_media_id: number | null; favicon_media_id: number | null }
  author: { name: string; bio: string; avatar_media_id: number | null; links: { label: string; kind: 'mail' | 'link'; url: string }[] }
  appearance: { theme: string; decor: { tape: boolean; doodles: boolean }; motion: string; code_theme: string; texts: { not_found_title: string; not_found_text: string; error_title: string; error_text: string } }
  seo: { title: string; description: string; keywords: string[]; share_image_media_id: number | null; robots_extra: string; sitemap: { moments: boolean; pages: boolean; taxonomy: boolean } }
  footer: { icp: string; copyright: string; text: string }
  stats: { enabled: boolean }
  backup: { enabled: boolean; hour: number; keep: number }
}
export type SettingsGroup = keyof SettingsGroups
export interface SettingsResponse { groups: SettingsGroups; defaults: SettingsGroups; vocab: Vocab; customized: string[] }

export interface HomeBlockAdmin { id: number | null; type: string; enabled: boolean; config: Record<string, unknown> }
export interface HomeAdmin { blocks: HomeBlockAdmin[]; customized: boolean; types: string[] }

export interface NavItemAdmin { id: number | null; region: string; label: string; kind: string; target: string; sticker: string | null; enabled: boolean }
export interface NavAdmin { top: { items: NavItemAdmin[]; customized: boolean }; mobile: { items: NavItemAdmin[]; customized: boolean }; footer: { items: NavItemAdmin[]; customized: boolean }; mobile_max: number }

export interface RedirectRow { id: number; source: string; target: string; status_code: 301 | 302; hits: number; last_hit_at: string | null; auto: boolean; created_at: string }

/* ---- overview, stats, logs, system ---- */
export interface Dashboard {
  stats: { posts: { published: number; draft: number; scheduled: number }; moments_month: number; views_7d: number; uniques_7d: number; storage: { media_bytes: number; db_bytes: number; backup_bytes: number } }
  views_series: { day: string; views: number; uniques: number }[]
  todo: { kind: string; id: number; title: string; admin_url: string }[]
  recent: { at: string; action: string; actor: string; target_type: string; target_id: string; summary: Record<string, unknown> }[]
  health: { version: string; build: string; db_bytes: number; disk_free: number; last_backup: { name?: string; at?: string; ok?: boolean } | string | null; schema_ok: boolean }
}
export interface StatsResponse {
  days: number; series: { day: string; views: number; uniques: number }[]; total_views: number; total_uniques: number
  top_posts: { id?: number; title: string; slug?: string; url?: string; views: number }[]; referrers: { domain: string; count: number }[]; devices: Record<string, number>
}
export interface AuditRow { id: number; at: string; actor: string; action: string; target_type: string; target_id: string; summary: Record<string, unknown>; ip_prefix: string }
export interface TrashItem { type: 'post' | 'moment' | 'page' | 'media'; id: number; title: string; deleted_at: string; expires_at: string; days_left: number }
export interface SystemStatus {
  version: string; build: string; env: string; uptime_seconds: number; python: string; sqlite: string; schema_revision: string; schema_head: string
  site_version: number; db_bytes: number; media_bytes: number; backup_bytes: number; disk: { total: number; free: number }; search_rows: number
  last_backup: { name?: string; at?: string } | null; backups: number; jobs: Record<string, { at?: string; ok?: boolean; result?: unknown }>; site_url: string
}
export interface BackupRow { name: string; bytes: number; created_at: string; label: string }
