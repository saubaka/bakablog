import { reactive } from 'vue'

export interface ToastItem { id: number; text: string; tone: 'ok' | 'warn' | 'error'; action?: { label: string; run: () => void } }
export const toasts = reactive<ToastItem[]>([])
let next = 1

/** A short message that disappears by itself (errors stay longer). Everything that saves says so: no silent success. */
export function toast(text: string, tone: ToastItem['tone'] = 'ok', action?: ToastItem['action']): void {
  const id = next++
  toasts.push({ id, text, tone, ...(action ? { action } : {}) })
  setTimeout(() => dismiss(id), tone === 'error' ? 7000 : action ? 8000 : 3200)
}
export const toastError = (text: string): void => toast(text, 'error')
export function dismiss(id: number): void {
  const i = toasts.findIndex((t) => t.id === id)
  if (i >= 0) toasts.splice(i, 1)
}
