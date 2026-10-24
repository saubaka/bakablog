<script setup lang="ts">
import EmptyBox from '../ui/EmptyBox.vue'
import PageHead from '../ui/PageHead.vue'
</script>

<template>
  <div>
    <PageHead title="找不到这一页" />
    <EmptyBox title="后台没有这个地址" text="可能是链接过期了，或者地址输错了。"><RouterLink class="btn btn--fill btn--sm" to="/">回到仪表盘</RouterLink></EmptyBox>
  </div>
</template>
