<script setup lang="ts">
/* One post as a card. The style comes from the post (card_style) or, for "auto", from where the card sits in the grid. */
import { computed } from 'vue'
import Phrase from '@/fx/Phrase'
import Icon from '@/ui/components/Icon'
import NavLink from '@/ui/components/NavLink.vue'
import type { PostCard } from '@/shared/types'
import type { CardLayout } from '../cards'
import { dot } from '../fmt'
import Cover from './Cover.vue'

const props = withDefaults(defineProps<{ post: PostCard; layout: CardLayout; level?: 2 | 3; eager?: boolean }>(), { level: 3, eager: false })

const heading = computed(() => `h${props.level}`)
const tags = computed(() => props.post.tags.slice(0, 3))
const sizes = computed(() => (props.layout === 'side' ? '(min-width: 1100px) 480px, 100vw' : '(min-width: 1100px) 360px, 100vw'))
</script>

<template>
  <NavLink class="card" :class="[`card--${layout}`, { 'card--has-cover': !!post.cover }]" :to="post.url">
    <span v-if="layout === 'note'" class="tape" />
    <Cover v-if="layout === 'side' || layout === 'cover' || layout === 'short' || layout === 'mini'" :media="post.cover" :alt="post.cover_alt" :focus="post.cover_focus" :seed="post.title" :sizes="sizes" :eager="eager" :short="layout === 'short' || layout === 'mini'">
      <span v-if="post.featured && layout === 'side'" class="badge cover__label"><Icon name="pin" />精选</span>
    </Cover>
    <span v-if="post.pinned && layout !== 'side'" class="badge card__pin"><Icon name="pin" />置顶</span>
    <div class="card__body">
      <Icon v-if="layout === 'quote'" name="quote" class="qmark" />
      <div v-if="layout !== 'quote' && layout !== 'mini' && layout !== 'short' && (post.category || tags.length)" class="card__tags">
        <span v-if="post.category" class="tag tag--rose">{{ post.category.name }}</span>
        <span v-for="t in tags" :key="t.id" class="tag">{{ t.name }}</span>
      </div>
      <component :is="heading" class="card__title"><Phrase :text="post.title" /></component>
      <p v-if="layout === 'side' || layout === 'cover' || layout === 'note'" class="card__sum">{{ post.summary }}</p>
      <div class="card__meta meta">
        <span v-if="layout === 'quote' && post.category" class="tag tag--sky">{{ post.category.name }}</span>
        <span><Icon name="calendar" /><time :datetime="post.published_at">{{ dot(post.published_at) }}</time></span>
        <span v-if="layout !== 'mini' && layout !== 'short' && post.reading_minutes"><Icon name="clock" />{{ post.reading_minutes }} 分钟</span>
      </div>
    </div>
  </NavLink>
</template>
