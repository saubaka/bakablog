<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { AdminError } from '../api/client'
import { setup } from '../auth'
import AIcon from '../ui/AIcon'
import Field from '../ui/Field.vue'
import { toast } from '../ui/toast'
import { useSubmit } from '../use'

const router = useRouter()
const token = ref('')
const username = ref('')
const password = ref('')
const again = ref('')
const email = ref('')
const message = ref('')
const { busy, fields, run } = useSubmit()

async function submit(): Promise<void> {
  message.value = ''
  if (password.value !== again.value) { message.value = '两次输入的密码不一样。'; return }
  try {
    await run(() => setup(token.value.trim(), username.value.trim(), password.value, email.value.trim() || undefined))
    toast('安装完成，已经登录。')
    await router.replace('/')
  } catch (e) {
    message.value = e instanceof AdminError ? (e.firstField ? `${e.message}${e.firstField ? `（${e.firstField}）` : ''}` : e.message) : '出了点问题，请再试一次。'
  }
}
</script>

<template>
  <main id="main" class="adm-auth" tabindex="-1">
    <form class="adm-auth__card adm-auth__card--wide" novalidate @submit.prevent="submit">
      <h1>首次安装</h1>
      <p class="adm-auth__lead">创建这个站点的管理员账号。这一页只会出现一次，创建完成后会永久关闭。</p>
      <Field v-slot="{ id }" label="安装口令" :error="fields.token" hint="在服务器启动日志里打印过一次；没看到的话，在服务器上运行 flask --app app setup-token 重新生成。">
        <input :id="id" v-model="token" class="input" name="token" autocomplete="off" spellcheck="false" required>
      </Field>
      <Field v-slot="{ id }" label="用户名" :error="fields.username" hint="3–32 位，字母、数字、下划线、点、短横线。">
        <input :id="id" v-model="username" class="input" name="username" autocomplete="username" autocapitalize="off" spellcheck="false" required>
      </Field>
      <Field v-slot="{ id }" label="密码" :error="fields.password" hint="至少 10 个字符，不要包含用户名，不要太好猜。">
        <input :id="id" v-model="password" class="input" name="password" type="password" autocomplete="new-password" required>
      </Field>
      <Field v-slot="{ id }" label="再输入一次密码">
        <input :id="id" v-model="again" class="input" name="again" type="password" autocomplete="new-password" required>
      </Field>
      <Field v-slot="{ id }" label="邮箱（可选）" :error="fields.email" hint="会放在“关于”里作为联系方式；这个站没有评论区，想说话的人只能写信。">
        <input :id="id" v-model="email" class="input" name="email" type="email" autocomplete="email">
      </Field>
      <p v-if="message" class="adm-auth__msg" role="alert"><AIcon name="alert" />{{ message }}</p>
      <button class="btn btn--fill adm-auth__go" type="submit" :disabled="busy || !token || !username || !password"><span v-if="busy">正在创建……</span><span v-else>创建管理员并登录</span></button>
    </form>
  </main>
</template>
