<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import CommandPalette from './CommandPalette.vue'
import SideNav from './SideNav.vue'
import TabBar from './TabBar.vue'
import TopBar from './TopBar.vue'
import { openPalette } from './palette'

/* Same page component = same instance (so a new post that becomes /posts/12 after its first save is not rebuilt under the author's cursor). */
function viewKey(name: unknown): string {
  if (name === 'post-new' || name === 'post-edit') return 'post-editor'
  if (name === 'page-new' || name === 'page-edit') return 'page-editor'
  return String(name)
}

function onKey(e: KeyboardEvent): void {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); openPalette() }
}
onMounted(() => document.addEventListener('keydown', onKey))
onBeforeUnmount(() => document.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="adm-shell">
    <SideNav />
    <div class="adm-col">
      <TopBar />
      <main id="main" class="adm-main" tabindex="-1">
        <RouterView v-slot="{ Component, route }">
          <component :is="Component" :key="viewKey(route.name)" />
        </RouterView>
      </main>
    </div>
    <TabBar />
    <CommandPalette />
  </div>
</template>
