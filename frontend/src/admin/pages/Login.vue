<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { AdminError } from '../api/client'
import { login } from '../auth'
import AIcon from '../ui/AIcon'
import Field from '../ui/Field.vue'
import { useSubmit } from '../use'

const route = useRoute()
const router = useRouter()
const username = ref('')
const password = ref('')
const code = ref('')
const needCode = ref(false)
const message = ref('')
const { busy, fields, run } = useSubmit()
const userEl = ref<HTMLInputElement | null>(null)
const codeEl = ref<HTMLInputElement | null>(null)

onMounted(() => userEl.value?.focus())

async function submit(): Promise<void> {
  message.value = ''
  try {
    await run(() => login(username.value.trim(), password.value, needCode.value ? code.value.trim() : undefined))
    const next = typeof route.query.next === 'string' && route.query.next.startsWith('/') ? route.query.next : '/'
    await router.replace(next)
  } catch (e) {
    if (!(e instanceof AdminError)) { message.value = '出了点问题，请再试一次。'; return }
    if (e.code === 'totp_required') { needCode.value = true; message.value = '请输入验证器里的 6 位动态码（或一次性恢复码）。'; await nextTick(); codeEl.value?.focus() }
    else if (e.code === 'bad_code') { message.value = e.message; code.value = ''; await nextTick(); codeEl.value?.focus() }
    else message.value = e.message
    password.value = e.code === 'totp_required' || e.code === 'bad_code' ? password.value : ''
  }
}
</script>

<template>
  <main id="main" class="adm-auth" tabindex="-1">
    <form class="adm-auth__card" novalidate @submit.prevent="submit">
      <h1>登录后台</h1>
      <p class="adm-auth__lead">这里是站长的工作台。</p>
      <Field v-slot="{ id }" label="用户名" :error="fields.username">
        <input :id="id" ref="userEl" v-model="username" class="input" name="username" autocomplete="username" autocapitalize="off" spellcheck="false" required>
      </Field>
      <Field v-slot="{ id }" label="密码" :error="fields.password">
        <input :id="id" v-model="password" class="input" name="password" type="password" autocomplete="current-password" required>
      </Field>
      <Field v-if="needCode" v-slot="{ id }" label="二次验证码" hint="验证器应用里的 6 位数字；手机丢了可以用一次性恢复码。">
        <input :id="id" ref="codeEl" v-model="code" class="input" name="code" inputmode="numeric" autocomplete="one-time-code" spellcheck="false">
      </Field>
      <p v-if="message" class="adm-auth__msg" role="alert"><AIcon name="alert" />{{ message }}</p>
      <button class="btn btn--fill adm-auth__go" type="submit" :disabled="busy || !username || !password"><span v-if="busy">正在登录……</span><span v-else>登录</span></button>
      <a class="text-link adm-auth__back" href="/"><AIcon name="arrow-l" />回到前台</a>
    </form>
  </main>
</template>
