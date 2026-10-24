<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { pending } from './confirm'

const dlg = ref<HTMLDialogElement | null>(null)
const typed = ref('')
const input = ref<HTMLInputElement | null>(null)

function close(ok: boolean): void {
  const p = pending.value
  if (!p) return
  if (ok && p.typeToConfirm && typed.value.trim() !== p.typeToConfirm) return
  pending.value = null
  p.resolve(ok)
}

watch(pending, async (p) => {
  const d = dlg.value
  if (!d) return
  if (p && !d.open) {
    typed.value = ''
    d.showModal()
    await nextTick()
    ;(input.value ?? d.querySelector<HTMLElement>('[data-autofocus]'))?.focus()
  } else if (!p && d.open) {
    d.close()
  }
})
</script>

<template>
  <dialog ref="dlg" class="dialog adm-confirm" :class="{ 'is-danger': pending?.danger }" aria-labelledby="adm-confirm-title" @cancel.prevent="close(false)" @click.self="close(false)">
    <form v-if="pending" method="dialog" @submit.prevent="close(true)">
      <h2 id="adm-confirm-title">{{ pending.title }}</h2>
      <p>{{ pending.text }}</p>
      <label v-if="pending.typeToConfirm" class="field adm-confirm__type">
        <span class="label">请输入 <b>{{ pending.typeToConfirm }}</b> 确认</span>
        <input ref="input" v-model="typed" class="input" autocomplete="off" spellcheck="false">
      </label>
      <div class="dialog__actions">
        <button class="btn btn--ghost" type="button" data-autofocus @click="close(false)">{{ pending.cancel }}</button>
        <button class="btn" :class="pending.danger ? 'btn--accent' : 'btn--fill'" type="submit" :disabled="!!pending.typeToConfirm && typed.trim() !== pending.typeToConfirm">{{ pending.confirm }}</button>
      </div>
    </form>
  </dialog>
</template>
