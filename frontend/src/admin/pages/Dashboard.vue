<script setup lang="ts">
import { computed } from 'vue'
import { api } from '../api/client'
import { ago, bytes } from '../format'
import { actionLabel, TARGET_LABEL, todoText } from '../labels'
import AIcon from '../ui/AIcon'
import EmptyBox from '../ui/EmptyBox.vue'
import PageHead from '../ui/PageHead.vue'
import Spark from '../ui/Spark.vue'
import { useLoader } from '../use'
import type { Dashboard } from '../types'

const { data, loading, error, reload } = useLoader((signal) => api.get<Dashboard>('/dashboard', undefined, signal))
const views = computed(() => data.value?.views_series.map((d) => d.views) ?? [])
const toLocal = (adminUrl: string): string => adminUrl.replace(/^\/admin/, '') || '/'
const backup = computed(() => {
  const b = data.value?.health.last_backup
  if (!b) return '还没有备份'
  if (typeof b === 'string') return ago(b)
  return b.at ? ago(b.at) : '有备份'
})
</script>

<template>
  <div>
    <PageHead title="仪表盘" sub="站点今天怎么样。">
      <RouterLink class="btn btn--fill" to="/posts/new"><AIcon name="a-edit" />写文章</RouterLink>
      <RouterLink class="btn" :to="{ path: '/moments', query: { compose: '1' } }"><AIcon name="chat" />发动态</RouterLink>
      <RouterLink class="btn" :to="{ path: '/media', query: { upload: '1' } }"><AIcon name="a-upload" />传图片</RouterLink>
    </PageHead>

    <p v-if="error" class="adm-error" role="alert">{{ error.message }} <button class="text-link" type="button" @click="reload">重试</button></p>
    <div v-else-if="loading && !data" class="adm-skel-grid" aria-busy="true"><span v-for="n in 4" :key="n" class="skel adm-skel" /></div>

    <template v-if="data">
      <section class="adm-stats" aria-label="概览">
        <RouterLink class="adm-card adm-stat" to="/posts"><small>已发布文章</small><b>{{ data.stats.posts.published }}</b><span>草稿 {{ data.stats.posts.draft }} · 定时 {{ data.stats.posts.scheduled }}</span></RouterLink>
        <RouterLink class="adm-card adm-stat" to="/moments"><small>本月动态</small><b>{{ data.stats.moments_month }}</b><span>碎碎念和随手拍</span></RouterLink>
        <RouterLink class="adm-card adm-stat" to="/stats">
          <small>7 日访问</small><b>{{ data.stats.views_7d }}</b>
          <Spark :values="views" label="最近 7 天每天的访问次数" /><span>估算独立访客 {{ data.stats.uniques_7d }}</span>
        </RouterLink>
        <RouterLink class="adm-card adm-stat" to="/system">
          <small>存储占用</small><b>{{ bytes(data.stats.storage.media_bytes + data.stats.storage.db_bytes + data.stats.storage.backup_bytes) }}</b>
          <span>图片 {{ bytes(data.stats.storage.media_bytes) }} · 数据库 {{ bytes(data.stats.storage.db_bytes) }}</span>
        </RouterLink>
      </section>

      <div class="adm-two">
        <section class="adm-card" aria-labelledby="todo-h">
          <h2 id="todo-h">待办提示</h2>
          <ul v-if="data.todo.length" class="adm-list">
            <li v-for="t in data.todo" :key="`${t.kind}${t.id ?? ''}`"><RouterLink :to="toLocal(t.admin_url)"><AIcon name="a-bell" /><span>{{ todoText(t) }}</span><AIcon name="a-chevron-r" class="adm-list__go" /></RouterLink></li>
          </ul>
          <EmptyBox v-else title="没有要处理的事" text="草稿都在动，图片都有替代文字。" />
        </section>

        <section class="adm-card" aria-labelledby="recent-h">
          <h2 id="recent-h">最近活动</h2>
          <ul v-if="data.recent.length" class="adm-list adm-list--plain">
            <li v-for="(r, i) in data.recent" :key="i">
              <span class="adm-recent__what"><b>{{ actionLabel(r.action) }}</b><small v-if="TARGET_LABEL[r.target_type] && r.target_id">{{ TARGET_LABEL[r.target_type] }} #{{ r.target_id }}</small></span>
              <small class="adm-recent__when">{{ r.actor }} · {{ ago(r.at) }}</small>
            </li>
          </ul>
          <EmptyBox v-else title="还没有活动记录" />
          <RouterLink class="text-link adm-more" to="/logs">全部日志<AIcon name="arrow-r" /></RouterLink>
        </section>
      </div>

      <section class="adm-card adm-health" aria-labelledby="health-h">
        <h2 id="health-h">系统健康</h2>
        <dl>
          <div><dt>版本</dt><dd>{{ data.health.version }}<small> · 构建 {{ data.health.build }}</small></dd></div>
          <div><dt>数据库</dt><dd>{{ bytes(data.health.db_bytes) }}<small> · {{ data.health.schema_ok ? '结构是最新的' : '结构需要升级' }}</small></dd></div>
          <div><dt>磁盘剩余</dt><dd>{{ bytes(data.health.disk_free) }}</dd></div>
          <div><dt>最近备份</dt><dd>{{ backup }}</dd></div>
        </dl>
        <RouterLink class="text-link" to="/backups">备份与恢复<AIcon name="arrow-r" /></RouterLink>
      </section>
    </template>
  </div>
</template>
