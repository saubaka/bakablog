<script setup lang="ts">
import { vFx } from '@/fx/directive'
import Icon from '@/ui/components/Icon'
import NavLink from '@/ui/components/NavLink.vue'
import type { Moment } from '@/shared/types'
import MomentView from '../../components/MomentView.vue'
import SectionSplit from './SectionSplit.vue'

defineProps<{ title: string; intro?: string; moments: Moment[]; id?: string }>()
</script>

<template>
  <SectionSplit :id="id" :title="title" :intro="intro">
    <template #label><NavLink class="text-link" to="/moments" v-fx="'fade'">看全部动态<Icon name="arrow-r" /></NavLink></template>
    <div class="moments-strip" data-fx-stagger>
      <MomentView v-for="m in moments" :key="m.id" :moment="m" />
    </div>
  </SectionSplit>
</template>
