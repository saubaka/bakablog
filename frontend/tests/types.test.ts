import { describe, expect, it } from 'vitest'
import archive from '@samples/archive.json'
import home from '@samples/home.json'
import moments from '@samples/moments.json'
import page from '@samples/page.json'
import post from '@samples/post.json'
import posts from '@samples/posts.json'
import search from '@samples/search.json'
import site from '@samples/site.json'
import taxonomy from '@samples/taxonomy.json'
import type { Archive, HomePayload, MomentsPage, PageDetail, PostDetail, PostsPage, SearchResult, SiteInfo, Taxonomy } from '@/shared/types'

/* The samples in docs/api-samples are the server's real answers (backend/scripts/dump_samples.py). Assigning them to the front end's types
   makes the type checker (npm run typecheck) fail when the server drops or renames a field the front end reads. */
const _site: SiteInfo = site as unknown as SiteInfo
const _home: HomePayload = home as unknown as HomePayload
const _posts: PostsPage = posts as unknown as PostsPage
const _post: PostDetail = post as unknown as PostDetail
const _archive: Archive = archive as unknown as Archive
const _taxonomy: Taxonomy = taxonomy as unknown as Taxonomy
const _moments: MomentsPage = moments as unknown as MomentsPage
const _page: PageDetail = page as unknown as PageDetail
const _search: SearchResult = search as unknown as SearchResult

describe('API samples match the front end types', () => {
  it('site: everything the app reads is present', () => {
    expect(_site.name).toBeTruthy()
    expect(_site.nav.top.length).toBeGreaterThan(0)
    expect(['default', 'sky', 'sakura', 'fog']).toContain(_site.theme)
    expect(['full', 'soft', 'off']).toContain(_site.motion)
    expect(['frost', 'blossom', 'fog']).toContain(_site.code_theme)
    expect(_site.texts.not_found_title).toBeTruthy()
    expect(_site.moods.length).toBe(10)
  })
  it('home blocks are the known types, in order', () => {
    const known = ['hero', 'notice', 'featured', 'latest_posts', 'latest_moments']
    for (const b of _home.blocks) expect(known).toContain(b.type)
    expect(_home.blocks[0]?.type).toBe('hero')
  })
  it('lists carry what the cards need', () => {
    for (const p of _posts.items) {
      expect(p.url).toBe(`/blog/${p.slug}`)
      expect(['auto', 'cover', 'side', 'note', 'quote']).toContain(p.card_style)
    }
    expect(_posts.filters).toHaveProperty('category')
    expect(_taxonomy.total_posts).toBeGreaterThan(0)
  })
  it('a post has html, toc, options, and neighbours', () => {
    expect(_post.html).toContain('<')
    expect(_post.toc.length).toBeGreaterThan(0)
    expect(_post.options).toHaveProperty('show_toc')
    expect(_post.seo.canonical).toMatch(/^https?:/)
  })
  it('archive, moments, page, search', () => {
    expect(_archive.years[0]?.months[0]?.posts.length).toBeGreaterThan(0)
    expect(_moments.meta?.months.length).toBeGreaterThan(0)
    expect(['plain', 'wide', 'sidebar']).toContain(_page.template)
    expect(_search.groups).toHaveProperty('posts')
  })
})
