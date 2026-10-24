<script setup lang="ts">
/* A labelled form row: label above, hint and error below, the control in the slot (which receives the id to put on it). */
import { useId } from 'vue'

defineProps<{ label: string; hint?: string; error?: string; required?: boolean }>()
const id = useId()
</script>

<template>
  <div class="field adm-field" :class="{ 'has-error': !!error }">
    <label class="label" :for="id">{{ label }}<span v-if="required" class="adm-req" aria-hidden="true"> *</span></label>
    <slot :id="id" :described-by="`${id}-d`" :invalid="!!error" />
    <small v-if="error" :id="`${id}-d`" class="adm-field__error" role="alert">{{ error }}</small>
    <small v-else-if="hint" :id="`${id}-d`">{{ hint }}</small>
  </div>
</template>
