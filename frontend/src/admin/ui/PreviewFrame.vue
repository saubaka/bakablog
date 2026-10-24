<script setup lang="ts">
/* A live look at unsaved settings: the real public components, drawn by /admin/preview-frame at the width of a phone, tablet or desktop and scaled
   to fit. The settings travel by postMessage (same origin only); the frame never asks the API about them. */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { isPreviewReady, PREVIEW_PATH, type PreviewMessage } from '@/preview/protocol'
import type { HomeBlock, SiteInfo } from '@/shared/types'
import Segmented from './Segmented.vue'

const props = defineProps<{ site: SiteInfo | null; home: HomeBlock[] | null; stale?: boolean }>()
type Device = 'phone' | 'tablet' | 'desktop'
const WIDTHS: Record<Device, number> = { phone: 390, tablet: 820, desktop: 1280 }
const chosen = ref<Device | null>(null)
const stage = ref<HTMLElement | null>(null)
const frame = ref<HTMLIFrameElement | null>(null)
const size = ref({ w: 0, h: 0 })
const ready = ref(false)
let observer: ResizeObserver | null = null

/* until the person picks one: the widest device that fits the pane without shrinking much */
const device = computed<Device>(() => chosen.value ?? (size.value.w >= 1000 ? 'desktop' : size.value.w >= 640 ? 'tablet' : 'phone'))
const width = computed(() => WIDTHS[device.value])
const scale = computed(() => (size.value.w > 0 ? Math.min(1, size.value.w / width.value) : 1))
const frameStyle = computed(() => ({
  width: `${width.value}px`,
  height: `${size.value.h / scale.value}px`,
  transform: `scale(${scale.value})`,
  left: `${Math.max(0, (size.value.w - width.value * scale.value) / 2)}px`,
}))

function send(): void {
  const target = frame.value?.contentWindow
  if (!ready.value || !target || !props.site || !props.home) return
  const message: PreviewMessage = { type: 'bb-preview', site: props.site, home: props.home }
  target.postMessage(JSON.parse(JSON.stringify(message)) as PreviewMessage, window.location.origin)
}
function onMessage(e: MessageEvent): void {
  if (e.origin !== window.location.origin || e.source !== frame.value?.contentWindow || !isPreviewReady(e.data)) return
  ready.value = true
  send()
}
watch(() => [props.site, props.home], send, { deep: true })
onMounted(() => {
  window.addEventListener('message', onMessage)
  if (stage.value) {
    observer = new ResizeObserver(([entry]) => { if (entry) size.value = { w: entry.contentRect.width, h: entry.contentRect.height } })
    observer.observe(stage.value)
  }
})
onBeforeUnmount(() => { window.removeEventListener('message', onMessage); observer?.disconnect() })
const options = [{ value: 'phone' as Device, label: '手机' }, { value: 'tablet' as Device, label: '平板' }, { value: 'desktop' as Device, label: '桌面' }]
</script>

<template>
  <div class="adm-pframe">
    <div class="adm-pframe__bar">
      <Segmented :model-value="device" label="预览宽度" :options="options" @update:model-value="(v) => (chosen = v)" />
      <small class="adm-hint" :class="{ 'is-stale': stale }" role="status">{{ stale ? '有一处设置还不合法，预览停在上一次的样子' : `${width}px 宽 · 未保存的改动也会在这里显示` }}</small>
    </div>
    <div ref="stage" class="adm-pframe__stage">
      <iframe ref="frame" class="adm-pframe__frame" :style="frameStyle" :src="PREVIEW_PATH" title="站点预览（只能看，不能点）" tabindex="-1" />
      <p v-if="!ready" class="adm-pframe__wait" role="status">正在准备预览……</p>
    </div>
  </div>
</template>
