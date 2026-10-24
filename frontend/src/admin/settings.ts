import { reactive } from 'vue'
import { api } from './api/client'
import type { SettingsGroup, SettingsGroups, SettingsResponse, Vocab } from './types'

/* The settings groups, loaded once per page that edits them. A save sends only one group; the answer is the stored group. */
export const settingsState = reactive({ groups: null as SettingsGroups | null, defaults: null as SettingsGroups | null, vocab: null as Vocab | null })

export async function loadSettings(): Promise<SettingsResponse> {
  const r = await api.get<SettingsResponse>('/settings')
  settingsState.groups = r.groups
  settingsState.defaults = r.defaults
  settingsState.vocab = r.vocab
  return r
}

export async function saveGroup<G extends SettingsGroup>(group: G, values: Partial<SettingsGroups[G]> | Record<string, unknown>): Promise<SettingsGroups[G]> {
  const r = await api.patch<{ values: SettingsGroups[G] }>(`/settings/${group}`, values)
  if (settingsState.groups) settingsState.groups[group] = r.values
  return r.values
}

export async function resetGroup<G extends SettingsGroup>(group: G): Promise<SettingsGroups[G]> {
  const r = await api.post<{ values: SettingsGroups[G] }>(`/settings/${group}/reset`)
  if (settingsState.groups) settingsState.groups[group] = r.values
  return r.values
}
