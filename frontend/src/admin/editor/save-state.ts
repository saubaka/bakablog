/** Accept canonical server values only where the author has not edited since submitting. */
export function afterSave<T extends object>(current: T, submitted: T, response: T): T {
  const next = { ...response }
  for (const key of Object.keys(submitted) as (keyof T)[]) {
    if (JSON.stringify(current[key]) !== JSON.stringify(submitted[key])) next[key] = current[key]
  }
  return next
}
