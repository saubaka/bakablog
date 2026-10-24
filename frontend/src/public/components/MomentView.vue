<script setup lang="ts">
/* One moment: the author's round picture and a speech bubble with the text, pictures, a link card, the mood, tags and the time. */
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { vFx } from '@/fx/directive'
import Icon from '@/ui/components/Icon'
import Mood from '@/ui/components/Mood.vue'
import type { Moment } from '@/shared/types'
import { when, day } from '../fmt'
import { internalLink } from '../links'
import { openLightbox } from '../lightbox'
import Avatar from './Avatar.vue'

const props = withDefaults(defineProps<{ moment: Moment; pinned?: boolean; permalink?: boolean; dx?: -1 | 1 }>(), { pinned: false, permalink: false, dx: -1 })
const router = useRouter()
const count = computed(() => props.moment.media.length)
const layout = computed(() => (count.value <= 1 ? 'n1' : count.value === 2 ? 'n2' : count.value === 3 ? 'n3' : count.value === 4 ? 'n4' : 'n6'))
const sizes = computed(() => (count.value === 1 ? '(min-width: 760px) 420px, 80vw' : '(min-width: 760px) 300px, 45vw'))
const fx = computed(() => ({ type: 'slide', dx: props.dx }) as const)

function open(i: number, e: MouseEvent): void {
  openLightbox(props.moment.media.map((m) => ({ src: m.full || m.src, alt: m.alt, caption: m.caption || m.alt })), i, e.currentTarget as HTMLElement)
}
</script>

<template>
  <article class="moment" :class="{ 'moment--pinned': pinned }" v-fx="fx">
    <Avatar />
    <div class="bubble moment__bubble">
      <span v-if="pinned" class="tape" />
      <p v-if="pinned" class="moment__pin"><Icon name="pin" />置顶</p>
      <div v-if="moment.html" class="moment__text" @click="internalLink($event, router)" v-html="moment.html" />
      <div v-if="count" class="moment__imgs" :class="layout">
        <button v-for="(m, i) in moment.media" :key="m.id" type="button" :aria-label="`查看图片：${m.alt || i + 1}`" @click="open(i, $event)">
          <img :src="m.src" :srcset="m.srcset || undefined" :sizes="m.srcset ? sizes : undefined" :alt="m.alt" :width="m.width" :height="m.height" :style="{ backgroundColor: m.color }" loading="lazy" decoding="async">
        </button>
      </div>
      <a v-if="moment.link_card" class="linkcard" :href="moment.link_card.url" target="_blank" rel="noopener noreferrer">
        <span class="linkcard__ico"><Icon name="link" /></span>
        <span><strong>{{ moment.link_card.title || moment.link_card.domain }}</strong><small>{{ moment.link_card.domain }}</small></span>
      </a>
      <div class="moment__foot">
        <Mood :mood="moment.mood" />
        <div v-if="moment.tags.length" class="tags">
          <RouterLink v-for="t in moment.tags" :key="t.id" class="tag tag--sky" :to="{ path: '/moments', query: { tag: t.slug } }">{{ t.name }}</RouterLink>
        </div>
        <component :is="permalink ? 'span' : 'RouterLink'" v-bind="permalink ? {} : { to: moment.url }" class="moment__time">
          <Icon name="clock" /><time :datetime="moment.published_at" :title="day(moment.published_at)">{{ when(moment.published_at) }}</time>
        </component>
      </div>
    </div>
  </article>
</template>
