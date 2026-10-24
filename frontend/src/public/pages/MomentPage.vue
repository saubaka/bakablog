<script setup lang="ts">
import { vFx } from '@/fx/directive'
import FxText from '@/fx/FxText.vue'
import Icon from '@/ui/components/Icon'
import NavLink from '@/ui/components/NavLink.vue'
import MomentView from '../components/MomentView.vue'
import type { PageState } from '../state'

defineProps<{ state: Extract<PageState, { kind: 'moment' }> }>()
</script>

<template>
  <div class="wrap wrap--read">
    <header class="page-head">
      <nav class="meta" aria-label="面包屑" v-fx="{ type: 'fade', intro: 0 }"><NavLink class="text-link" to="/moments"><Icon name="arrow-l" />动态</NavLink></nav>
      <FxText tag="h1" text="一条动态" :intro="1" />
    </header>
    <div class="moment-single">
      <MomentView :moment="state.data" permalink :dx="1" />
    </div>
  </div>
</template>
