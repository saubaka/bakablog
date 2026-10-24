<script setup lang="ts">
/* The foot of every page: only the legal line (copyright, and the filing number when the site has one). The brand block, the "browse" and the
   "subscribe and contact" columns are gone on purpose (2026-10-24, the user asked for them to be removed from every page). */
import { computed } from 'vue'
import { site } from '../state'

const year = new Date().getFullYear()
const copyright = computed(() => site.value.footer.copyright || `© ${year} ${site.value.author.name} · ${site.value.name_en}`)
</script>

<template>
  <footer class="site-footer">
    <div class="wrap">
      <div class="site-footer__legal" v-fx="'fade'">
        <span>{{ copyright }}<template v-if="!site.footer.copyright"> · 没有评论区，想说什么请发邮件</template></span>
        <a v-if="site.footer.icp" href="https://beian.miit.gov.cn/" target="_blank" rel="noopener noreferrer">{{ site.footer.icp }}</a>
      </div>
    </div>
  </footer>
</template>
