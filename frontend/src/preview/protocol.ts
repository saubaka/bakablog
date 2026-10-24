import type { HomeBlock, SiteInfo } from '@/shared/types'

/** What the admin page tells the preview frame (same origin only): the site settings and the home blocks as visitors would get them. */
export interface PreviewMessage { type: 'bb-preview'; site: SiteInfo; home: HomeBlock[] }
/** The frame says hello when it has loaded, so the admin can send the first picture. */
export interface PreviewReady { type: 'bb-preview-ready' }

export const PREVIEW_PATH = '/admin/preview-frame'

export function isPreviewMessage(data: unknown): data is PreviewMessage {
  return typeof data === 'object' && data !== null && (data as { type?: unknown }).type === 'bb-preview'
}
export function isPreviewReady(data: unknown): data is PreviewReady {
  return typeof data === 'object' && data !== null && (data as { type?: unknown }).type === 'bb-preview-ready'
}
