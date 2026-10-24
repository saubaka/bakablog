import { shallowRef } from 'vue'

export interface ConfirmRequest {
  title: string
  text: string
  confirm: string
  cancel: string
  danger: boolean
  /** Dangerous and hard to undo: the person must type this word first. */
  typeToConfirm: string
  resolve: (ok: boolean) => void
}
export const pending = shallowRef<ConfirmRequest | null>(null)

/** Ask before something that cannot be undone. Resolves true / false; the dialog says what will happen (docs/PLAN.md 5.4). */
export function confirm(opts: { title: string; text: string; confirm?: string; cancel?: string; danger?: boolean; typeToConfirm?: string }): Promise<boolean> {
  return new Promise((resolve) => {
    pending.value?.resolve(false)
    pending.value = { title: opts.title, text: opts.text, confirm: opts.confirm ?? '确定', cancel: opts.cancel ?? '取消', danger: opts.danger ?? false, typeToConfirm: opts.typeToConfirm ?? '', resolve }
  })
}
