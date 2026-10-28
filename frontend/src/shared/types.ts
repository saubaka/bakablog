/* Shapes of the public JSON API. Written against docs/api-samples/*.json; tests/types.test.ts assigns every sample to these
   types, so a field that the server stops sending (or renames) fails the type check. */

export interface MediaVariant { size: number; w: number; h: number; url: string }

export interface Media {
  id: number
  alt: string
  caption: string
  width: number
  height: number
  color: string
  animated: boolean
  src: string
  srcset: string
  full: string
  variants: MediaVariant[]
}

export interface Category { id: number; slug: string; name: string; description: string; sticker: string | null; url: string }
export interface CategoryCount extends Category { count: number; show_on_shelf: boolean }

export type TagColor = 'sky' | 'rose' | 'mist' | 'white'
export interface Tag { id: number; slug: string; name: string; color: TagColor; sticker: string | null; url: string }
export interface TagCount extends Tag { count: number; moment_count: number; size?: number }

export type SeriesStatus = 'ongoing' | 'finished'
export interface SeriesRef { id: number; slug: string; title: string; order: number }
export interface Series { id: number; slug: string; title: string; description: string; status: SeriesStatus; cover: Media | null; url: string }
export interface SeriesCount extends Series { count: number }

export type CardStyle = 'auto' | 'cover' | 'side' | 'note' | 'quote'

export interface PostCard {
  id: number
  slug: string
  url: string
  title: string
  summary: string
  cover: Media | null
  cover_alt: string
  cover_focus: { x: number; y: number }
  category: Category | null
  tags: Tag[]
  series: SeriesRef | null
  pinned: boolean
  featured: boolean
  card_style: CardStyle
  published_at: string
  updated_at: string
  reading_minutes: number
  word_count: number
  snippet?: string
}

/** Previous / next / related entries are lighter than a card. */
export interface PostMini {
  id: number
  slug: string
  url: string
  title: string
  summary: string
  cover: Media | null
  published_at: string
  category: Category | null
  reading_minutes: number
}

export interface TocEntry { id: string; text: string; level: number }

export interface Seo {
  title: string
  description: string
  image: Media | null
  canonical: string
  noindex: boolean
}

export interface SeriesNav {
  id: number
  slug: string
  title: string
  status: SeriesStatus
  total: number
  index: number
  items: { slug: string; title: string; order: number; current: boolean }[]
}

export interface PostDetail extends PostCard {
  html: string
  toc: TocEntry[]
  options: { show_toc: boolean; show_reading_time: boolean; show_author_card: boolean }
  prev: PostMini | null
  next: PostMini | null
  related: PostMini[]
  series_nav: SeriesNav | null
  status: string
  preview: boolean
  seo: Seo
}

export interface PostFilters { category: Category | null; tag: Tag | null; series: Series | null; q: string | null }
export interface PostsPage {
  items: PostCard[]
  total: number
  page: number
  per: number
  pages: number
  filters: PostFilters
}

export interface ArchiveMonth { month: number; count: number; posts: PostCard[] }
export interface ArchiveYear { year: number; count: number; months: ArchiveMonth[] }
export interface Archive { years: ArchiveYear[]; total: number }

export interface Taxonomy { categories: CategoryCount[]; tags: TagCount[]; series: SeriesCount[]; total_posts: number }

export interface Mood { id: string; label: string }
export interface LinkCard { url: string; title: string; description: string; domain: string; icon: string | null }
export interface Moment {
  id: number
  url: string
  html: string
  text: string
  mood: Mood | null
  tags: Tag[]
  media: Media[]
  link_card: LinkCard | null
  pinned: boolean
  published_at: string
  snippet?: string
}
export interface MomentsMeta {
  months: { month: string; count: number }[]
  days: Record<string, number[]>
  tags: (Tag & { count: number })[]
  moods: { id: string; label: string; count: number }[]
}
export interface MomentsPage { items: Moment[]; next_cursor: string | null; pinned?: Moment[]; meta?: MomentsMeta }

export interface PageDetail {
  id: number
  slug: string
  url: string
  title: string
  html: string
  toc: TocEntry[]
  template: 'plain' | 'wide' | 'sidebar'
  updated_at: string
  seo: Seo
}

export interface SearchResult {
  q: string
  type: 'all' | 'post' | 'moment' | 'page'
  total: number
  groups: { posts: PostCard[]; moments: Moment[]; pages: (PageHit)[] }
}
export interface PageHit { id: number; slug: string; url: string; title: string; snippet: string }

/* ---- home blocks ---------------------------------------------------------------------------------------------------------- */
export interface HeroButton { label: string; url: string; style: 'fill' | 'line' | 'link' }
export type DoodleName = 'star' | 'heart' | 'sparkle' | 'flower' | 'paw' | 'wave' | 'loop'
export interface Author { name: string; bio: string; avatar: Media | null; links: { label: string; kind: 'mail' | 'link'; url: string }[] }

export interface HeroConfig {
  note: string
  intro: string
  buttons: HeroButton[]
  doodles: DoodleName[]
}
export type HomeBlock =
  | { type: 'hero'; id: number | null; config: HeroConfig; data: Record<string, never> }
  | { type: 'notice'; id: number | null; config: { text: string; starts_at: string | null; ends_at: string | null }; data: Record<string, never> }
  | { type: 'featured'; id: number | null; config: { title: string; mode: 'auto' | 'manual'; post_ids: number[]; count: number }; data: { posts: PostCard[] } }
  | { type: 'latest_posts'; id: number | null; config: { title: string; intro: string; count: number; layout: 'mixed' | 'list' | 'grid' }; data: { posts: PostCard[] } }
  | { type: 'latest_moments'; id: number | null; config: { title: string; intro: string; count: number }; data: { moments: Moment[] } }
export interface HomePayload { blocks: HomeBlock[]; site_version: number }

/* ---- site ----------------------------------------------------------------------------------------------------------------- */
export type ThemeName = 'default' | 'sky' | 'sakura' | 'fog'
export type MotionLevel = 'full' | 'soft' | 'off'
export type CodeTheme = 'frost' | 'blossom' | 'fog'

export interface NavItem {
  id: number | null
  label: string
  kind: 'route' | 'page' | 'category' | 'tag' | 'series' | 'link' | 'action'
  url: string
  action: 'search' | 'more' | 'top' | null
  sticker: string | null
  external: boolean
}

export interface SiteInfo {
  name: string
  name_en: string
  tagline: string
  description: string
  language: string
  timezone: string
  logo: Media | null
  favicon: Media | null
  author: Author
  theme: ThemeName
  decor: { tape: boolean; doodles: boolean }
  motion: MotionLevel
  code_theme: CodeTheme
  texts: { not_found_title: string; not_found_text: string; error_title: string; error_text: string }
  seo: { title: string; description: string; keywords: string[]; share_image: Media | null }
  footer: { icp: string; copyright: string; text: string }
  nav: { top: NavItem[]; mobile: NavItem[]; footer: NavItem[] }
  features: { stats: boolean; search: boolean }
  moods: Mood[]
  origin: string
  version: string
  build: string
  site_version: number
}

/* ---- what the server inlines on the first screen (docs/API.md section 4) ------------------------------------------------- */
export type PageKind = 'home' | 'blog' | 'post' | 'taxonomy' | 'archive' | 'moments' | 'moment' | 'page' | 'search' | '404' | '500'
export interface BootData {
  path: string
  kind: PageKind
  status: number
  site: SiteInfo
  data: unknown
}

export interface ApiErrorBody { error: { code: string; message: string; fields?: Record<string, string>; location?: string } }
