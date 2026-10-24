/* Small accessibility fixes for server-rendered article HTML, shared by the public page and the admin's preview. */

/** A task-list checkbox has no label of its own: use the text of its list item. */
export function labelTasks(box: ParentNode): void {
  box.querySelectorAll<HTMLInputElement>('input.task-list-item-checkbox').forEach((input) => {
    input.setAttribute('aria-label', (input.closest('li')?.textContent ?? '').trim().slice(0, 80) || '任务')
  })
}

/** A code block or table wider than the column scrolls sideways; the keyboard must be able to reach it. */
export function markScrollable(box: ParentNode): void {
  box.querySelectorAll<HTMLElement>('pre, .table-wrap').forEach((el) => {
    if (el.scrollWidth > el.clientWidth + 1) {
      el.tabIndex = 0
      if (!el.hasAttribute('role')) el.setAttribute('role', 'group')
      if (!el.hasAttribute('aria-label')) el.setAttribute('aria-label', el.matches('pre') ? '代码（可横向滚动）' : '表格（可横向滚动）')
    } else {
      el.removeAttribute('tabindex'); el.removeAttribute('role'); el.removeAttribute('aria-label')
    }
  })
}
