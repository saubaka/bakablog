<script setup lang="ts">
import { computed } from 'vue'
import { vFx } from '@/fx/directive'
import FxText from '@/fx/FxText.vue'
import Doodle from '@/ui/components/Doodle.vue'
import Icon from '@/ui/components/Icon'
import NavLink from '@/ui/components/NavLink.vue'
import type { HeroConfig } from '@/shared/types'
import { iconFor } from '../../nav'
import { ICONS } from '../../icons'
import { site } from '../../state'

defineProps<{ config: HeroConfig }>()
/** The big title is the name of the site, the English name under it. */
const title = computed(() => [site.value.name, site.value.name_en.toUpperCase()].filter(Boolean))
const buttonIcon = (url: string, style: string): string | null => (style === 'link' ? iconFor({ id: null, label: '', kind: 'link', url, action: null, sticker: null, external: false }, ICONS) : null)
</script>

<template>
  <section class="hero">
    <div class="wrap hero__grid">
      <div class="hero__copy">
        <span v-if="config.note" class="kicker" v-fx="{ type: 'pop', intro: 0 }"><Icon name="sparkle" />{{ config.note }}</span>
        <FxText tag="h1" class="hero__title" :lines="title" highlight-last :intro="1" />
        <p v-if="config.intro" class="hero__lead" v-fx="{ type: 'fade', intro: 3 }">{{ config.intro }}</p>
        <div v-if="config.buttons.length" class="hero__actions" v-fx="{ type: 'fade', intro: 4 }">
          <NavLink v-for="b in config.buttons" :key="b.url + b.label" :to="b.url" :class="b.style === 'link' ? 'text-link' : b.style === 'fill' ? 'btn btn--fill' : 'btn'">
            <Icon v-if="buttonIcon(b.url, b.style)" :name="buttonIcon(b.url, b.style) as string" />{{ b.label }}<Icon v-if="b.style === 'fill'" name="arrow-r" />
          </NavLink>
        </div>
      </div>
      <div class="hero__visual" aria-hidden="true">
        <Doodle v-for="(d, i) in config.doodles" :key="d" :name="d" :class="`doodle--${'abc'[i]}`" :drift="[-34, 28, -22][i]" />
      </div>
    </div>
  </section>
</template>
