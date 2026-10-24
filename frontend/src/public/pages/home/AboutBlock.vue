<script setup lang="ts">
import { vFx } from '@/fx/directive'
import Icon from '@/ui/components/Icon'
import NavLink from '@/ui/components/NavLink.vue'
import type { Author } from '@/shared/types'
import Avatar from '../../components/Avatar.vue'
import NowNote from './NowNote.vue'
import SectionSplit from './SectionSplit.vue'

defineProps<{ title: string; intro?: string; text: string[]; author: Author; now: { title: string; items: { icon: string; text: string }[] } | null; id?: string }>()
const href = (url: string): string => (url.includes('@') && !/^[a-z]+:/i.test(url) && !url.startsWith('/') ? `mailto:${url}` : url)
const icon = (kind: string): string => (kind === 'mail' ? 'mail' : kind === 'rss' ? 'rss' : 'link')
</script>

<template>
  <SectionSplit :id="id" :title="title" :intro="intro">
    <div class="about">
      <div class="about__card" v-fx="'rise'">
        <Avatar large />
        <div>
          <h3>{{ author.name }}</h3>
          <p v-for="(p, i) in (text.length ? text : [author.bio])" :key="i">{{ p }}</p>
          <div v-if="author.links.length" class="about__links">
            <NavLink v-for="l in author.links" :key="l.url" class="btn btn--sm" :to="href(l.url)"><Icon :name="icon(l.kind)" />{{ l.label }}</NavLink>
          </div>
        </div>
      </div>
      <NowNote v-if="now" :title="now.title" :items="now.items" />
    </div>
  </SectionSplit>
</template>
