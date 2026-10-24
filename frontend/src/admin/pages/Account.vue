<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { copyText } from '@/shared/clipboard'
import { api, AdminError } from '../api/client'
import { auth, loadMe } from '../auth'
import { ago, when } from '../format'
import type { AdminSession, AdminUser, LoginRecord } from '../types'
import AIcon from '../ui/AIcon'
import { confirm } from '../ui/confirm'
import Field from '../ui/Field.vue'
import TableWrap from '../ui/TableWrap.vue'
import PageHead from '../ui/PageHead.vue'
import { toast, toastError } from '../ui/toast'
import { useSubmit } from '../use'

const user = computed(() => auth.user as AdminUser)
const sessions = ref<AdminSession[]>([])
const logins = ref<LoginRecord[]>([])
const message = (e: unknown, fallback = '没有成功。'): string => (e instanceof AdminError ? e.message : fallback)

async function loadLists(): Promise<void> {
  try {
    const [s, l] = await Promise.all([api.get<{ items: AdminSession[] }>('/auth/sessions'), api.get<{ items: LoginRecord[] }>('/auth/logins')])
    sessions.value = s.items
    logins.value = l.items
  } catch (e) { toastError(message(e, '列表加载失败。')) }
}
onMounted(loadLists)

/* ---- user name ---- */
const nameForm = reactive({ username: auth.user?.username ?? '', password: '' })
const nameSubmit = useSubmit()
async function saveName(): Promise<void> {
  try {
    await nameSubmit.run(() => api.patch('/auth/me', { username: nameForm.username.trim(), password: nameForm.password }))
    nameForm.password = ''
    await loadMe()
    toast('用户名已修改。')
  } catch (e) { if (!(e instanceof AdminError && e.status === 422)) toastError(message(e)) }
}

/* ---- password ---- */
const pwForm = reactive({ current_password: '', new_password: '', again: '' })
const pwSubmit = useSubmit()
const pwMismatch = computed(() => pwForm.again !== '' && pwForm.again !== pwForm.new_password)
async function savePassword(): Promise<void> {
  if (pwForm.new_password !== pwForm.again) return
  try {
    await pwSubmit.run(() => api.post('/auth/password', { current_password: pwForm.current_password, new_password: pwForm.new_password }))
    Object.assign(pwForm, { current_password: '', new_password: '', again: '' })
    toast('密码已修改，其他设备已经退出登录。')
    await loadLists()
  } catch (e) { if (!(e instanceof AdminError && e.status === 422)) toastError(message(e)) }
}

/* ---- two-step verification ---- */
const setupInfo = ref<{ secret: string; uri: string } | null>(null)
const code = ref('')
const codes = ref<string[]>([])
const disablePw = ref('')
const totpSubmit = useSubmit()
const grouped = computed(() => (setupInfo.value?.secret.match(/.{1,4}/g) ?? []).join(' '))
async function begin(): Promise<void> {
  try { setupInfo.value = await api.post<{ secret: string; uri: string }>('/auth/totp/begin'); code.value = '' } catch (e) { toastError(message(e)) }
}
async function enable(): Promise<void> {
  try {
    const out = await totpSubmit.run(() => api.post<{ recovery_codes: string[] }>('/auth/totp/enable', { code: code.value.trim() }))
    if (out) { codes.value = out.recovery_codes; setupInfo.value = null; await loadMe(); toast('二次验证已开启。') }
  } catch (e) { if (!(e instanceof AdminError && e.status === 422)) toastError(message(e)) }
}
async function disable(): Promise<void> {
  if (!(await confirm({ title: '关闭二次验证？', text: '之后只用密码就能登录。', confirm: '关闭', danger: true }))) return
  try { await totpSubmit.run(() => api.post('/auth/totp/disable', { password: disablePw.value })); disablePw.value = ''; await loadMe(); toast('二次验证已关闭。') } catch (e) { if (!(e instanceof AdminError && e.status === 422)) toastError(message(e)) }
}
async function copyCodes(): Promise<void> { toast((await copyText(codes.value.join('\n'))) ? '已复制恢复码。' : '复制没有成功，请手动选中抄下来。') }

/* ---- sessions ---- */
async function revoke(s: AdminSession): Promise<void> {
  if (!(await confirm({ title: `让「${s.device}」下线？`, text: '那台设备需要重新登录。', confirm: '让它下线', danger: true }))) return
  try { await api.del(`/auth/sessions/${s.id}`); toast('已下线。'); await loadLists() } catch (e) { toastError(message(e)) }
}
async function revokeOthers(): Promise<void> {
  if (!(await confirm({ title: '让其他设备都下线？', text: '只保留你现在用的这个。', confirm: '全部下线', danger: true }))) return
  try { const out = await api.post<{ revoked: number }>('/auth/sessions/revoke-others'); toast(`已让 ${out.revoked} 个会话下线。`); await loadLists() } catch (e) { toastError(message(e)) }
}
const REASON: Record<string, string> = { ok: '成功', bad_credentials: '用户名或密码不对', bad_code: '动态码不对', totp_required: '需要二次验证', locked: '被暂时锁定', recovery: '用了恢复码' }
</script>

<template>
  <div>
    <PageHead title="账号与安全" sub="用户名、密码、二次验证，以及登录过的设备。" />
    <div class="adm-stack">
      <form class="adm-card adm-section" @submit.prevent="saveName">
        <h2>用户名</h2>
        <div class="adm-form adm-form--2">
          <Field v-slot="{ id }" label="用户名" :error="nameSubmit.fields.value.username" hint="3–32 个字符"><input :id="id" v-model="nameForm.username" class="input" autocomplete="username" maxlength="32"></Field>
          <Field v-slot="{ id }" label="当前密码" :error="nameSubmit.fields.value.password" hint="改用户名需要再输一次密码"><input :id="id" v-model="nameForm.password" class="input" type="password" autocomplete="current-password"></Field>
        </div>
        <div class="adm-section__foot"><button class="btn btn--fill" type="submit" :disabled="nameSubmit.busy.value || !nameForm.password || nameForm.username === user.username"><AIcon name="a-save" />保存用户名</button></div>
      </form>

      <form class="adm-card adm-section" @submit.prevent="savePassword">
        <h2>密码</h2>
        <div class="adm-form adm-form--2">
          <Field v-slot="{ id }" label="当前密码" class="span-2" :error="pwSubmit.fields.value.current_password"><input :id="id" v-model="pwForm.current_password" class="input" type="password" autocomplete="current-password"></Field>
          <Field v-slot="{ id }" label="新密码" :error="pwSubmit.fields.value.new_password" hint="至少 10 个字符；用密码管理器生成最好"><input :id="id" v-model="pwForm.new_password" class="input" type="password" autocomplete="new-password"></Field>
          <Field v-slot="{ id }" label="再输一次" :error="pwMismatch ? '两次输入不一样' : undefined"><input :id="id" v-model="pwForm.again" class="input" type="password" autocomplete="new-password"></Field>
        </div>
        <div class="adm-section__foot"><button class="btn btn--fill" type="submit" :disabled="pwSubmit.busy.value || !pwForm.current_password || !pwForm.new_password || pwMismatch"><AIcon name="a-save" />修改密码</button></div>
      </form>

      <section class="adm-card adm-section" aria-labelledby="totp-h">
        <h2 id="totp-h">二次验证（动态码）</h2>
        <template v-if="codes.length">
          <p class="adm-hint">二次验证已经开启。下面是 10 个一次性恢复码：手机丢了、没法生成动态码的时候，可以用其中一个代替（每个只能用一次）。<b>只显示这一次</b>，请现在就存到密码管理器里。</p>
          <ul class="adm-codes" aria-label="一次性恢复码"><li v-for="c in codes" :key="c">{{ c }}</li></ul>
          <div class="adm-section__foot"><button class="btn" type="button" @click="copyCodes"><AIcon name="copy" />复制全部</button><button class="btn btn--fill" type="button" @click="codes = []">我已经存好了</button></div>
        </template>
        <template v-else-if="user.totp_enabled">
          <p class="adm-hint"><span class="adm-badge adm-badge--ok">已开启</span> 登录时除了密码，还需要验证器 App 里的 6 位动态码。</p>
          <form class="adm-form adm-form--2" @submit.prevent="disable">
            <Field v-slot="{ id }" label="关闭需要输入密码" :error="totpSubmit.fields.value.password"><input :id="id" v-model="disablePw" class="input" type="password" autocomplete="current-password"></Field>
            <div class="adm-formbtn"><button class="btn btn--danger" type="submit" :disabled="totpSubmit.busy.value || !disablePw">关闭二次验证</button></div>
          </form>
        </template>
        <template v-else-if="setupInfo">
          <ol class="adm-steps">
            <li>在验证器 App（任何支持 TOTP 的都行）里选“手动输入密钥”，填入：<code class="adm-secret">{{ grouped }}</code>
              <small>在手机上也可以直接 <a :href="setupInfo.uri">点这里在验证器里打开</a>。</small></li>
            <li>输入 App 现在显示的 6 位数字，确认设置正确：</li>
          </ol>
          <form class="adm-form adm-form--2" @submit.prevent="enable">
            <Field v-slot="{ id }" label="6 位动态码" :error="totpSubmit.fields.value.code"><input :id="id" v-model="code" class="input" inputmode="numeric" autocomplete="one-time-code" maxlength="8" placeholder="123456"></Field>
            <div class="adm-formbtn"><button class="btn btn--fill" type="submit" :disabled="totpSubmit.busy.value || code.trim().length < 6">确认并开启</button><button class="btn btn--ghost" type="button" @click="setupInfo = null">取消</button></div>
          </form>
        </template>
        <template v-else>
          <p class="adm-hint">没有开启。开启后即使密码泄露，别人也登不进来。</p>
          <div class="adm-section__foot"><button class="btn btn--fill" type="button" @click="begin">开始设置</button></div>
        </template>
      </section>

      <section class="adm-card adm-section" aria-labelledby="sess-h">
        <h2 id="sess-h">登录过的设备</h2>
        <TableWrap label="表格">
          <table class="adm-table">
            <thead><tr><th>设备</th><th>网段</th><th class="is-nowrap">最近活动</th><th class="is-nowrap">到期</th><th class="is-shrink"><span class="sr-only">操作</span></th></tr></thead>
            <tbody>
              <tr v-for="s in sessions" :key="s.id">
                <td>{{ s.device }} <span v-if="s.current" class="adm-badge adm-badge--ok">当前设备</span></td>
                <td class="adm-mono">{{ s.ip_prefix || '—' }}</td><td class="is-nowrap">{{ ago(s.last_seen_at) }}</td><td class="is-nowrap">{{ when(s.expires_at).slice(0, 10) }}</td>
                <td class="is-nowrap"><button v-if="!s.current" class="btn btn--sm btn--ghost" type="button" @click="revoke(s)">让它下线</button></td>
              </tr>
            </tbody>
          </table>
        </TableWrap>
        <div class="adm-section__foot"><button class="btn" type="button" :disabled="sessions.length < 2" @click="revokeOthers">让其他设备都下线</button></div>
      </section>

      <section class="adm-card adm-section" aria-labelledby="log-h">
        <h2 id="log-h">最近的登录记录</h2>
        <TableWrap label="表格2">
          <table class="adm-table">
            <thead><tr><th class="is-nowrap">时间</th><th>结果</th><th>网段</th><th>浏览器</th></tr></thead>
            <tbody>
              <tr v-for="(l, i) in logins" :key="i">
                <td class="is-nowrap">{{ when(l.at) }}</td>
                <td><span class="adm-badge" :class="l.success ? 'adm-badge--ok' : 'adm-badge--rose'">{{ REASON[l.reason] ?? l.reason }}</span></td>
                <td class="adm-mono">{{ l.ip_prefix || '—' }}</td><td class="adm-clip">{{ l.user_agent || '—' }}</td>
              </tr>
              <tr v-if="!logins.length"><td colspan="4" class="adm-hint">还没有记录。</td></tr>
            </tbody>
          </table>
        </TableWrap>
      </section>
    </div>
  </div>
</template>
