/** Copy text. The asynchronous clipboard API needs a permission some browsers never answer (it then hangs instead of failing),
    so it gets 800 ms; after that the old selection-based copy is tried. Returns whether anything was copied. */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      const done = await Promise.race([
        navigator.clipboard.writeText(text).then(() => true),
        new Promise<boolean>((resolve) => setTimeout(() => resolve(false), 800)),
      ])
      if (done) return true
    }
  } catch { /* fall through to the selection-based copy */ }
  const area = document.createElement('textarea')
  area.value = text
  area.setAttribute('readonly', '')
  area.className = 'sr-only'
  document.body.append(area)
  area.select()
  let ok = false
  try { ok = document.execCommand('copy') } catch { ok = false }
  area.remove()
  return ok
}
