<script setup lang="ts">
/* A heading whose characters enter one after another with the scroll.
   Rendered declaratively (no DOM surgery after the fact), so Vue and the engine never fight over the same text nodes:
   - words from Intl.Segmenter stay together, lines break only between words;
   - the element carries the whole sentence as aria-label, the pieces are aria-hidden;
   - longer than 32 characters (24 on a phone) it simply fades in as one block. */
import { computed } from 'vue'
import { useViewport } from '@/public/viewport'
import { vFx } from './directive'
import { charOffset } from './math'
import { plain, words, graphemes, canSplit } from './text'

const props = withDefaults(defineProps<{
  tag?: string
  text?: string
  /** Several lines (a hero title): joined by line breaks. */
  lines?: string[]
  /** The last line gets the marker underline. */
  highlightLast?: boolean
  intro?: number
}>(), { tag: 'h2', text: '', lines: () => [], highlightLast: false, intro: undefined })

const { narrow } = useViewport()

const parts = computed(() => (props.lines.length ? props.lines : [props.text]).map(plain).filter(Boolean))
const label = computed(() => parts.value.join(' '))
const split = computed(() => canSplit(label.value, narrow.value))

interface Word { chars: { c: string; o: number }[]; gapAfter: boolean; space: boolean }
const lines = computed(() => {
  const total = parts.value.reduce((n, p) => n + graphemes(p.replace(/\s+/g, '')).length, 0)
  let at = 0
  return parts.value.map((p, li) => {
    const toks = words(p)
    const ws: Word[] = toks.map((tk, i) => {
      if (tk.space) return { chars: [], gapAfter: false, space: true }
      const chars = graphemes(tk.t).map((c) => ({ c, o: charOffset(at++, total) }))
      const next = toks[i + 1]
      return { chars, gapAfter: !!next && !next.space, space: false }
    })
    return { words: ws, hl: props.highlightLast && li === parts.value.length - 1 }
  })
})
const fxType = computed(() => (split.value ? 'text' : 'fade'))
const opts = computed(() => ({ type: fxType.value, ...(props.intro !== undefined ? { intro: props.intro } : {}) }) as const)
</script>

<template>
  <!-- the key makes a changed sentence a fresh element: the engine measures it again from scratch -->
  <component :is="tag" :key="label" v-fx="opts" :aria-label="split ? label : undefined">
    <template v-if="split">
      <template v-for="(line, li) in lines" :key="li">
        <br v-if="li > 0">
        <component :is="line.hl ? 'em' : 'span'" :class="line.hl ? 'hl has-split' : 'fx-line'">
          <template v-for="(w, wi) in line.words" :key="wi">
            <template v-if="w.space">{{ ' ' }}</template>
            <template v-else>
              <span class="fx-w" aria-hidden="true"><span v-for="(ch, ci) in w.chars" :key="ci" class="fx-c" :style="{ '--co': ch.o }">{{ ch.c }}</span></span><wbr v-if="w.gapAfter">
            </template>
          </template>
        </component>
      </template>
    </template>
    <template v-else>
      <template v-for="(line, li) in lines" :key="li">
        <br v-if="li > 0">
        <component :is="line.hl ? 'em' : 'span'" :class="line.hl ? 'hl' : 'fx-line'">{{ parts[li] }}</component>
      </template>
    </template>
  </component>
</template>
