<script setup lang="ts">
import { computed, ref } from 'vue'
import { vFx } from '@/fx/directive'
import FxText from '@/fx/FxText.vue'
import Phrase from '@/fx/Phrase'
import Icon from '@/ui/components/Icon'
import NavLink from '@/ui/components/NavLink.vue'
import Avatar from '../components/Avatar.vue'
import Cover from '../components/Cover.vue'
import MiniCard from '../components/MiniCard.vue'
import ProseView from '../components/ProseView.vue'
import ReadBar from '../components/ReadBar.vue'
import Stamp from '../components/Stamp.vue'
import Toc from '../components/Toc.vue'
import { day, dot } from '../fmt'
import { site, type PageState } from '../state'

const props = defineProps<{ state: Extract<PageState, { kind: 'post' }> }>()
const post = computed(() => props.state.data)
const prose = ref<InstanceType<typeof ProseView> | null>(null)
const proseEl = computed(() => prose.value?.el ?? null)
const updated = computed(() => (day(post.value.updated_at) > day(post.value.published_at) ? post.value.updated_at : ''))
const seriesLink = computed(() => (post.value.series_nav ? `/series/${post.value.series_nav.slug}` : ''))
</script>

<template>
  <article>
    <ReadBar :target="proseEl" />
    <div class="wrap post-layout">
      <header class="post-head">
        <nav class="meta" aria-label="面包屑" v-fx="{ type: 'fade', intro: 0 }"><NavLink class="text-link" to="/blog"><Icon name="arrow-l" />博客</NavLink></nav>
        <div class="card__tags" v-fx="{ type: 'pop', intro: 1 }">
          <NavLink v-if="post.category" class="tag tag--rose" :to="post.category.url"><Icon name="folder" />{{ post.category.name }}</NavLink>
          <NavLink v-for="t in post.tags" :key="t.id" class="tag" :to="t.url">{{ t.name }}</NavLink>
        </div>
        <FxText tag="h1" :text="post.title" :intro="2" />
        <div class="meta" v-fx="{ type: 'fade', intro: 3 }">
          <Stamp :iso="post.published_at" small />
          <span v-if="post.options.show_reading_time"><Icon name="clock" />{{ post.reading_minutes }} 分钟读完</span>
          <span v-if="updated"><Icon name="calendar" />更新于 <time :datetime="updated">{{ dot(updated) }}</time></span>
          <span v-if="post.options.show_author_card"><Icon name="smile" />{{ site.author.name }}</span>
          <span v-if="post.preview" class="badge"><Icon name="alert" />预览中 · {{ post.status }}</span>
        </div>
      </header>

      <div class="post-main">
        <div class="post-cover" v-fx="{ type: 'mask', radius: 28 }">
          <Cover :media="post.cover" :alt="post.cover_alt" :focus="post.cover_focus" :seed="post.title" sizes="(min-width: 1100px) 720px, 100vw" eager />
        </div>

        <ProseView ref="prose" :html="post.html" />

        <div class="post-foot">
          <section v-if="post.series_nav" class="series" v-fx="'rise'" aria-label="系列">
            <div class="series__head">
              <h2>系列：<NavLink class="series__link" :to="seriesLink">{{ post.series_nav.title }}</NavLink></h2>
              <span class="tag tag--rose">{{ post.series_nav.status === 'finished' ? '已完结' : '连载中' }} {{ post.series_nav.index }} / {{ post.series_nav.total }}</span>
            </div>
            <ol>
              <li v-for="it in post.series_nav.items" :key="it.slug" :aria-current="it.current ? 'step' : undefined">
                <span v-if="it.current"><Phrase :text="it.title" /></span>
                <NavLink v-else :to="`/blog/${it.slug}`"><Phrase :text="it.title" /></NavLink>
              </li>
            </ol>
          </section>

          <nav v-if="post.prev || post.next" class="pn" aria-label="上一篇和下一篇" data-fx-stagger>
            <NavLink v-if="post.prev" v-fx="'rise'" class="pn__prev" :to="post.prev.url"><small><Icon name="arrow-l" />上一篇</small><strong><Phrase :text="post.prev.title" /></strong></NavLink>
            <span v-else />
            <NavLink v-if="post.next" v-fx="'rise'" class="pn__next" :to="post.next.url"><small>下一篇<Icon name="arrow-r" /></small><strong><Phrase :text="post.next.title" /></strong></NavLink>
          </nav>

          <div v-if="post.options.show_author_card" class="authorbox" v-fx="'rise'">
            <Avatar large />
            <div><strong>{{ site.author.name }}</strong><p>{{ site.author.bio }}</p></div>
          </div>

          <section v-if="post.related.length" aria-label="相关文章">
            <h2 class="related__title" v-fx="'fade'">相关文章</h2>
            <div class="related" data-fx-stagger>
              <MiniCard v-for="r in post.related" :key="r.id" v-fx="'rise'" :post="r" />
            </div>
          </section>
        </div>
      </div>

      <Toc v-if="post.options.show_toc" :entries="post.toc" />
    </div>
  </article>
</template>
