<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AdminSprite from './ui/AdminSprite.vue'
import ConfirmHost from './ui/ConfirmHost.vue'
import ToastHost from './ui/ToastHost.vue'
import { auth } from './auth'
import Shell from './layout/Shell.vue'

const route = useRoute()
const bare = computed(() => !!route.meta.open || !auth.user)
</script>

<template>
  <AdminSprite />
  <a class="skip-link" href="#main">跳到正文</a>
  <template v-if="auth.ready">
    <RouterView v-if="bare" />
    <Shell v-else />
  </template>
  <p v-else class="adm-boot" role="status">正在打开后台……</p>
  <ToastHost />
  <ConfirmHost />
</template>
