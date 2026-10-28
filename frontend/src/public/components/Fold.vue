<script setup lang="ts">
/* Something that comes and goes (a "filter is on" chip, the result tabs once there is a query): it opens to its height and fades in, and folds shut when it goes,
   so what is below it slides instead of jumping. The height is animated by CSS alone (a grid row from 0fr to 1fr), nothing is measured. */
defineProps<{ show: boolean }>()
</script>

<template>
  <Transition name="fold">
    <div v-if="show" class="fold"><div class="fold__in"><slot /></div></div>
  </Transition>
</template>
