<script setup lang="ts">
import { computed } from 'vue'
import { vFx } from '@/fx/directive'
import FxText from '@/fx/FxText.vue'
import Doodle from '@/ui/components/Doodle.vue'
import Icon from '@/ui/components/Icon'
import NavLink from '@/ui/components/NavLink.vue'
import type { HeroConfig } from '@/shared/types'
import { stampOf } from '../../fmt'
import { iconFor } from '../../nav'
import { ICONS } from '../../icons'

const props = defineProps<{ config: HeroConfig }>()
const today = computed(() => stampOf(new Date().toISOString()))
const media = computed(() => props.config.polaroid.media)
const buttonIcon = (url: string, style: string): string | null => (style === 'link' ? iconFor({ id: null, label: '', kind: 'link', url, action: null, sticker: null, external: false }, ICONS) : null)
</script>

<template>
  <section class="hero">
    <div class="wrap hero__grid">
      <div class="hero__copy">
        <span v-if="config.note" class="kicker" v-fx="{ type: 'pop', intro: 0 }"><Icon name="sparkle" />{{ config.note }}</span>
        <FxText tag="h1" class="hero__title" :lines="config.title_lines" highlight-last :intro="1" />
        <p v-if="config.intro" class="hero__lead" v-fx="{ type: 'fade', intro: 3 }">{{ config.intro }}</p>
        <div v-if="config.buttons.length" class="hero__actions" v-fx="{ type: 'fade', intro: 4 }">
          <NavLink v-for="b in config.buttons" :key="b.url + b.label" :to="b.url" :class="b.style === 'link' ? 'text-link' : b.style === 'fill' ? 'btn btn--fill' : 'btn'">
            <Icon v-if="buttonIcon(b.url, b.style)" :name="buttonIcon(b.url, b.style) as string" />{{ b.label }}<Icon v-if="b.style === 'fill'" name="arrow-r" />
          </NavLink>
        </div>
      </div>
      <div class="hero__visual">
        <Doodle v-for="(d, i) in config.doodles" :key="d" :name="d" :class="`doodle--${'abc'[i]}`" :drift="[-34, 28, -22][i]" />
        <figure class="polaroid polaroid--hero" v-fx="{ type: 'pop', intro: 2, rot: 5 }">
          <span class="tape tape--top" />
          <div class="polaroid__pic" :class="media ? '' : 'cv-sky cv-dots'">
            <img v-if="media" :src="media.src" :srcset="media.srcset || undefined" sizes="(min-width: 1100px) 330px, 260px" :width="media.width" :height="media.height" :alt="media.alt" :style="{ backgroundColor: media.color }" decoding="async">
            <Icon v-else name="heart" class="polaroid__blank" />
          </div>
          <figcaption v-if="config.polaroid.caption">{{ config.polaroid.caption }}</figcaption>
          <div class="stamp" aria-hidden="true"><b>{{ today.day }}</b><small>{{ today.mon }}</small></div>
        </figure>
        <div v-if="config.polaroid.bubble" class="bubble bubble--pop hero__say" v-fx="{ type: 'pop', intro: 5, rot: -4 }">{{ config.polaroid.bubble }}</div>
      </div>
    </div>
  </section>
</template>
