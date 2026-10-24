<script setup lang="ts">
import { useRouter } from 'vue-router'
import { auth, logout } from '../auth'
import AIcon from '../ui/AIcon'
import Menu from '../ui/Menu.vue'
import { toast } from '../ui/toast'
import { openPalette } from './palette'

const router = useRouter()
async function signOut(): Promise<void> {
  await logout()
  toast('已退出登录。')
  await router.replace({ name: 'login' })
}
</script>

<template>
  <header class="adm-top">
    <button class="adm-top__search" type="button" aria-label="搜索或跳转（Ctrl / ⌘ K）" @click="openPalette">
      <AIcon name="search" /><span>搜索或跳转……</span><kbd>⌘K</kbd>
    </button>
    <div class="adm-top__tools">
      <Menu label="新建" icon="a-plus" primary>
        <RouterLink role="menuitem" to="/posts/new"><AIcon name="book" />文章</RouterLink>
        <RouterLink role="menuitem" :to="{ path: '/moments', query: { compose: '1' } }"><AIcon name="chat" />动态</RouterLink>
        <RouterLink role="menuitem" to="/pages/new"><AIcon name="smile" />页面</RouterLink>
        <RouterLink role="menuitem" :to="{ path: '/media', query: { upload: '1' } }"><AIcon name="a-upload" />上传图片</RouterLink>
      </Menu>
      <a class="btn btn--ghost adm-top__view" href="/" target="_blank" rel="noopener" aria-label="查看前台（在新标签页打开）"><AIcon name="external" /><span>查看前台</span></a>
      <Menu :label="auth.user?.username ?? '账号'" icon="a-user" icon-only>
        <div class="adm-menu__who"><b>{{ auth.user?.username }}</b><small>{{ auth.user?.role === 'owner' ? '站长' : auth.user?.role }}</small></div>
        <RouterLink role="menuitem" to="/account"><AIcon name="a-shield" />账号与安全</RouterLink>
        <button role="menuitem" type="button" @click="signOut"><AIcon name="a-logout" />退出登录</button>
      </Menu>
    </div>
  </header>
</template>
