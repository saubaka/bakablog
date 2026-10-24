/* Dates. The server sends UTC ("2026-10-18T09:30:00Z"); "which day" and "which month" are decided by the site's time zone. */

const MONTHS_EN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'] as const

export interface DayParts { year: number; month: number; day: number; hour: number; minute: number }

const cache = new Map<string, Intl.DateTimeFormat>()
function formatter(tz: string): Intl.DateTimeFormat {
  let f = cache.get(tz)
  if (!f) {
    try {
      f = new Intl.DateTimeFormat('en-US', { timeZone: tz, hourCycle: 'h23', year: 'numeric', month: 'numeric', day: 'numeric', hour: 'numeric', minute: 'numeric' })
    } catch {
      f = new Intl.DateTimeFormat('en-US', { hourCycle: 'h23', year: 'numeric', month: 'numeric', day: 'numeric', hour: 'numeric', minute: 'numeric' })
    }
    cache.set(tz, f)
  }
  return f
}

export function parts(iso: string | null | undefined, tz: string): DayParts | null {
  if (!iso) return null
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return null
  const o: Record<string, number> = {}
  for (const p of formatter(tz).formatToParts(new Date(t))) if (p.type !== 'literal') o[p.type] = Number(p.value)
  return { year: o.year ?? 0, month: o.month ?? 0, day: o.day ?? 0, hour: o.hour === 24 ? 0 : o.hour ?? 0, minute: o.minute ?? 0 }
}

const pad = (n: number): string => String(n).padStart(2, '0')

/** 2026.10.18 */
export function dotDate(iso: string | null | undefined, tz: string): string {
  const p = parts(iso, tz)
  return p ? `${p.year}.${pad(p.month)}.${pad(p.day)}` : ''
}

/** 2026-10-18 (the datetime attribute of <time>) */
export function isoDay(iso: string | null | undefined, tz: string): string {
  const p = parts(iso, tz)
  return p ? `${p.year}-${pad(p.month)}-${pad(p.day)}` : ''
}

/** The day stamp: { day: "18", mon: "Oct", month: 10 } */
export function stamp(iso: string | null | undefined, tz: string): { day: string; mon: string; month: number; year: number } {
  const p = parts(iso, tz)
  if (!p) return { day: '', mon: '', month: 0, year: 0 }
  return { day: pad(p.day), mon: MONTHS_EN[p.month - 1] ?? '', month: p.month, year: p.year }
}

/** "2026 年 10 月 18 日" */
export function longDate(iso: string | null | undefined, tz: string): string {
  const p = parts(iso, tz)
  return p ? `${p.year} 年 ${p.month} 月 ${p.day} 日` : ''
}

/** "今天 10:12" · "昨天 22:40" · "10 月 12 日" · "2025 年 3 月 4 日" */
export function momentTime(iso: string, tz: string, now: Date = new Date()): string {
  const p = parts(iso, tz)
  const n = parts(now.toISOString(), tz)
  if (!p || !n) return ''
  const hm = `${pad(p.hour)}:${pad(p.minute)}`
  const dayNo = (d: DayParts): number => Math.floor(Date.UTC(d.year, d.month - 1, d.day) / 86_400_000)
  const diff = dayNo(n) - dayNo(p)
  if (diff === 0) return `今天 ${hm}`
  if (diff === 1) return `昨天 ${hm}`
  if (p.year === n.year) return `${p.month} 月 ${p.day} 日`
  return `${p.year} 年 ${p.month} 月 ${p.day} 日`
}

/** "2026-10" for a timestamp: the month group of the moments timeline. */
export function monthKey(iso: string, tz: string): string {
  const p = parts(iso, tz)
  return p ? `${p.year}-${pad(p.month)}` : ''
}

/** "2026 年 10 月" from "2026-10" */
export function monthLabel(key: string): string {
  const m = /^(\d{4})-(\d{2})$/.exec(key)
  return m ? `${m[1]} 年 ${Number(m[2])} 月` : key
}

export function readingTime(minutes: number): string {
  return minutes <= 1 ? '1 分钟' : `${minutes} 分钟`
}
