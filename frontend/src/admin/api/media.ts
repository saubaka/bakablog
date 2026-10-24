import { AdminError, csrf } from './client'
import type { AdminMedia } from '../types'

/** Upload one picture with progress (fetch cannot report upload progress, XMLHttpRequest can). The same content returns the same picture. */
export function uploadMedia(file: File, opts: { alt?: string; onProgress?: (fraction: number) => void; signal?: AbortSignal } = {}): Promise<AdminMedia & { duplicate: boolean }> {
  return new Promise((resolve, reject) => {
    const form = new FormData()
    form.append('file', file)
    if (opts.alt) form.append('alt', opts.alt)
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/admin/media')
    xhr.setRequestHeader('X-CSRF-Token', csrf.value)
    xhr.setRequestHeader('Accept', 'application/json')
    xhr.responseType = 'json'
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) opts.onProgress?.(e.loaded / e.total) }
    xhr.onerror = () => reject(new AdminError(0, 'network', '连不上服务器，请检查网络后再试。'))
    xhr.onabort = () => reject(new DOMException('aborted', 'AbortError'))
    xhr.onload = () => {
      const body = xhr.response as Record<string, unknown> | null
      if (xhr.status >= 200 && xhr.status < 300 && body) { resolve(body as unknown as AdminMedia & { duplicate: boolean }); return }
      const e = (body?.error ?? {}) as { code?: string; message?: string; fields?: Record<string, string> }
      reject(new AdminError(xhr.status, e.code ?? `http_${xhr.status}`, e.message ?? (xhr.status === 413 ? '文件太大了。' : '上传没有成功。'), e.fields ?? {}))
    }
    opts.signal?.addEventListener('abort', () => xhr.abort())
    xhr.send(form)
  })
}

export function mediaThumb(m: Pick<AdminMedia, 'variants' | 'src'>, size = 480): string {
  return m.variants.find((v) => v.size === size)?.url ?? m.variants[0]?.url ?? m.src
}
