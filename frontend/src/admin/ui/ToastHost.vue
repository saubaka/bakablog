<script setup lang="ts">
import AIcon from './AIcon'
import { dismiss, toasts } from './toast'
</script>

<template>
  <div class="adm-toasts" role="region" aria-label="通知" aria-live="polite">
    <div v-for="t in toasts" :key="t.id" class="toast" :class="{ 'toast--rose': t.tone !== 'ok' }" :role="t.tone === 'error' ? 'alert' : 'status'">
      <span class="toast__ico"><AIcon :name="t.tone === 'ok' ? 'check' : 'alert'" /></span>
      <span class="adm-toast__text">{{ t.text }}</span>
      <button v-if="t.action" class="btn btn--sm btn--ghost" type="button" @click="t.action.run(); dismiss(t.id)">{{ t.action.label }}</button>
      <button class="icon-btn icon-btn--ghost adm-toast__x" type="button" aria-label="关闭" @click="dismiss(t.id)"><AIcon name="close" /></button>
    </div>
  </div>
</template>
