<script setup lang="ts">
/* The sidebar. A click does three things in order, each once: the group opens (if it was shut), the pill glides to the item, the page changes.
   Browser back / forward moves the pill the same way. Groups remember whether they were open. */
import { nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AIcon from '../ui/AIcon'
import { entryFor, NAV, type NavEntry } from '../nav'

const route = useRoute()
const router = useRouter()
const box = ref<HTMLElement | null>(null)
const pill = reactive({ y: 0, h: 0, shown: false, ready: false })
const open = reactive<Record<string, boolean>>(readOpen())
const target = ref<string>(entryFor(route.path)?.to ?? '')
let timer = 0

function readOpen(): Record<string, boolean> {
  try { return JSON.parse(localStorage.getItem('bb:admin-nav') || '{}') as Record<string, boolean> } catch { return {} }
}
const isOpen = (id: string): boolean => open[id] !== false
function toggle(id: string): void {
  open[id] = !isOpen(id)
  try { localStorage.setItem('bb:admin-nav', JSON.stringify(open)) } catch { /* optional */ }
  void nextTick().then(() => window.setTimeout(place, 280))
}

function place(): void {
  const el = box.value?.querySelector<HTMLElement>(`a[data-to="${CSS.escape(target.value)}"]`)
  const nav = box.value
  if (!el || !nav || el.offsetParent === null) { pill.shown = false; return }
  const a = el.getBoundingClientRect()
  const b = nav.getBoundingClientRect()
  pill.y = a.top - b.top + nav.scrollTop
  pill.h = a.height
  pill.shown = true
}

const reduced = (): boolean => window.matchMedia('(prefers-reduced-motion: reduce)').matches

function go(e: MouseEvent, entry: NavEntry): void {
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return
  e.preventDefault()
  if (entry.to === route.path) return
  target.value = entry.to
  place()                                                // one glide, straight to the item
  window.clearTimeout(timer)
  timer = window.setTimeout(() => { void router.push(entry.to) }, reduced() ? 0 : 230)
}

watch(() => route.path, (p) => { target.value = entryFor(p)?.to ?? ''; void nextTick().then(place) })
onMounted(() => {
  place()
  requestAnimationFrame(() => requestAnimationFrame(() => { pill.ready = true }))
  void document.fonts?.ready.then(() => { pill.ready = false; place(); requestAnimationFrame(() => { pill.ready = true }) })
  window.addEventListener('resize', place, { passive: true })
})
onBeforeUnmount(() => { window.clearTimeout(timer); window.removeEventListener('resize', place) })
</script>

<template>
  <aside class="adm-side" aria-label="后台导航">
    <RouterLink class="adm-brand" to="/">
      <span><b>管理后台</b><small>Baka Blog</small></span>
    </RouterLink>
    <nav ref="box" class="adm-nav">
      <i class="adm-nav__pill" :class="{ 'is-shown': pill.shown, 'is-ready': pill.ready }" :style="{ '--y': `${pill.y}px`, '--h': `${pill.h}px` }" aria-hidden="true" />
      <section v-for="g in NAV" :key="g.id" class="adm-nav__group" :class="{ 'is-open': isOpen(g.id) }">
        <button class="adm-nav__head" type="button" :aria-expanded="isOpen(g.id)" :aria-controls="`nav-${g.id}`" @click="toggle(g.id)">
          <span>{{ g.label }}</span><AIcon name="a-chevron-d" />
        </button>
        <div :id="`nav-${g.id}`" class="adm-nav__items" :inert="isOpen(g.id) ? undefined : true">
          <ul>
            <li v-for="it in g.items" :key="it.to">
              <RouterLink :to="it.to" custom v-slot="{ href }">
                <a :href="href" :data-to="it.to" :aria-current="entryFor(route.path)?.to === it.to ? 'page' : undefined" @click="go($event, it)"><AIcon :name="it.icon" />{{ it.label }}</a>
              </RouterLink>
            </li>
          </ul>
        </div>
      </section>
    </nav>
  </aside>
</template>
