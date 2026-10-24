import { reactive } from 'vue'
import { api } from './api/client'
import type { AdminCategory, AdminSeries, AdminTag } from './types'

/* Categories, tags and series are needed all over the admin (filters, the editor's side panel, the palette): loaded once, refreshed after changes. */
export const taxo = reactive({ categories: [] as AdminCategory[], tags: [] as AdminTag[], series: [] as AdminSeries[], loaded: false })
let inflight: Promise<void> | null = null

export function loadTaxonomy(force = false): Promise<void> {
  if (taxo.loaded && !force) return Promise.resolve()
  inflight ??= Promise.all([
    api.get<{ items: AdminCategory[] }>('/taxonomy/categories'),
    api.get<{ items: AdminTag[] }>('/taxonomy/tags'),
    api.get<{ items: AdminSeries[] }>('/taxonomy/series'),
  ]).then(([c, t, s]) => {
    taxo.categories = c.items
    taxo.tags = t.items
    taxo.series = s.items
    taxo.loaded = true
  }).finally(() => { inflight = null })
  return inflight
}
