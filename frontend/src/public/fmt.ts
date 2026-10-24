import { dotDate, isoDay, longDate, momentTime, monthKey, stamp } from '@/shared/format'
import { site } from './state'

/* The date helpers with the site's time zone filled in. Call them from templates: they read the (reactive) site settings. */
export const dot = (iso: string | null | undefined): string => dotDate(iso, site.value.timezone)
export const day = (iso: string | null | undefined): string => isoDay(iso, site.value.timezone)
export const long = (iso: string | null | undefined): string => longDate(iso, site.value.timezone)
export const stampOf = (iso: string | null | undefined) => stamp(iso, site.value.timezone)
export const when = (iso: string): string => momentTime(iso, site.value.timezone)
export const monthOf = (iso: string): string => monthKey(iso, site.value.timezone)
