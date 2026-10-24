<script setup lang="ts">
/* The public page's frame (header, home, footer, bottom bar) around whatever the admin sends: a live look at unsaved settings. */
import Sprite from '@/ui/components/Sprite.vue'
import SiteFooter from '@/public/layout/SiteFooter.vue'
import SiteHeader from '@/public/layout/SiteHeader.vue'
import TabBar from '@/public/layout/TabBar.vue'
import Home from '@/public/pages/Home.vue'
import { page } from '@/public/state'
</script>

<template>
  <Sprite />
  <SiteHeader />
  <main id="main">
    <Home v-if="page && page.kind === 'home'" :state="page" />
  </main>
  <SiteFooter />
  <TabBar />
</template>
