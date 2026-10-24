<script setup lang="ts">
/* A link that is a router link when the address belongs to this app, and an ordinary link otherwise
   (feeds, mailto:, other sites, the admin shell). Either way it is an <a href>: it works in a new tab and without scripts. */
import { computed } from 'vue'
import { isServerPath } from '@/public/router'

defineOptions({ inheritAttrs: false })
const props = defineProps<{ to: string; external?: boolean; current?: boolean }>()
const outside = computed(() => !!props.external || /^[a-z][a-z0-9+.-]*:/i.test(props.to) || props.to.startsWith('//') || isServerPath(props.to))
const newTab = computed(() => /^https?:/i.test(props.to) && props.external !== false)
</script>

<template>
  <a v-if="outside" v-bind="$attrs" :href="to" :aria-current="current ? 'page' : undefined" :target="newTab ? '_blank' : undefined" :rel="newTab ? 'noopener noreferrer' : undefined"><slot /></a>
  <RouterLink v-else :to="to" custom v-slot="{ href, navigate }">
    <a v-bind="$attrs" :href="href" :aria-current="current ? 'page' : undefined" @click="navigate"><slot /></a>
  </RouterLink>
</template>
