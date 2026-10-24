import { describe, expect, it } from 'vitest'
import { dotDate, isoDay, longDate, momentTime, monthKey, monthLabel, parts, readingTime, stamp } from '@/shared/format'

const TZ = 'Asia/Shanghai'

describe('dates follow the site time zone', () => {
  it('a UTC late evening is already the next day in Shanghai', () => {
    expect(dotDate('2026-10-18T17:30:00Z', TZ)).toBe('2026.10.19')
    expect(dotDate('2026-10-18T17:30:00Z', 'UTC')).toBe('2026.10.18')
    expect(isoDay('2026-10-18T17:30:00Z', TZ)).toBe('2026-10-19')
    expect(longDate('2026-10-18T09:30:00Z', TZ)).toBe('2026 年 10 月 18 日')
  })

  it('the day stamp', () => {
    expect(stamp('2026-10-05T01:00:00Z', TZ)).toEqual({ day: '05', mon: 'Oct', month: 10, year: 2026 })
    expect(stamp(null, TZ)).toEqual({ day: '', mon: '', month: 0, year: 0 })
  })

  it('midnight is hour 0, not 24', () => {
    expect(parts('2026-10-17T16:00:00Z', TZ)?.hour).toBe(0)
  })

  it('an unknown time zone falls back instead of throwing', () => {
    expect(dotDate('2026-10-18T09:30:00Z', 'Mars/Olympus')).toMatch(/^2026\.10\.1[78]$/)
  })

  it('moments: today, yesterday, this year, other years', () => {
    const now = new Date('2026-10-22T04:00:00Z')    // 12:00 in Shanghai
    expect(momentTime('2026-10-22T02:12:00Z', TZ, now)).toBe('今天 10:12')
    expect(momentTime('2026-10-21T14:40:00Z', TZ, now)).toBe('昨天 22:40')
    expect(momentTime('2026-10-12T15:05:00Z', TZ, now)).toBe('10 月 12 日')
    expect(momentTime('2025-03-04T01:00:00Z', TZ, now)).toBe('2025 年 3 月 4 日')
  })

  it('month keys and labels', () => {
    expect(monthKey('2026-09-30T20:00:00Z', TZ)).toBe('2026-10')
    expect(monthLabel('2026-09')).toBe('2026 年 9 月')
    expect(monthLabel('nonsense')).toBe('nonsense')
  })

  it('bad input gives empty strings, never "NaN"', () => {
    expect(dotDate('not a date', TZ)).toBe('')
    expect(dotDate(undefined, TZ)).toBe('')
    expect(readingTime(0)).toBe('1 分钟')
    expect(readingTime(8)).toBe('8 分钟')
  })
})
