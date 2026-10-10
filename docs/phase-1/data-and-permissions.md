# 数据模型与权限

## 1. 数据建模原则

- 使用SQLite兼容的数据类型和约束，不依赖特定大型数据库特性。
- 所有业务表使用统一主键、创建时间和修改时间。
- 公开内容使用稳定`slug`或不可猜测ID，发布后不随标题自动变化。
- 重要内容采用软删除；关联表和临时记录按业务需要硬删除。
- 时间统一以UTC保存，Jinja2展示时转换为站点时区。
- 布尔状态、发布状态和审核状态使用受控枚举值并由应用层校验。
- 联系方式、IP、内部备注和审核信息永不进入公开序列化结果。

## 2. 核心实体

### 2.1 身份与权限

| 实体 | 关键字段 | 关键约束/索引 |
| --- | --- | --- |
| `users` | username, email, password_hash, is_active, last_login_at | username/email唯一；active索引 |
| `roles` | name, description | name唯一 |
| `permissions` | code, description | code唯一 |
| `user_roles` | user_id, role_id | 联合唯一；双向外键索引 |
| `role_permissions` | role_id, permission_id | 联合唯一；双向外键索引 |
| `login_logs` | user_id, success, ip_hash, user_agent, created_at | user/time索引 |
| `audit_logs` | actor_id, action, entity_type, entity_id, detail, created_at | entity/time与actor/time索引 |

### 2.2 博客

| 实体 | 关键字段 | 关键约束/索引 |
| --- | --- | --- |
| `posts` | title, slug, summary, body_source, body_html, status, published_at, author_id, cover_media_id | slug唯一；status/published复合索引 |
| `post_versions` | post_id, version_no, title, body_source, editor_id, created_at | post/version唯一 |
| `categories` | name, slug, description, sort_order | slug唯一；sort索引 |
| `tags` | name, slug | name和slug唯一 |
| `post_categories` | post_id, category_id | 联合唯一；双向索引 |
| `post_tags` | post_id, tag_id | 联合唯一；双向索引 |
| `redirects` | source_path, target_path, status_code | source唯一 |

### 2.3 个人内容

| 实体 | 关键字段 | 关键约束/索引 |
| --- | --- | --- |
| `profiles` | display_name, bio, avatar_media_id, location, contact_config | 单站点只允许一条有效记录 |
| `experiences` | type, title, organization, start_date, end_date, description, sort_order | type/sort索引 |
| `skills` | name, group_name, level, sort_order | group/sort索引 |
| `projects` | title, slug, summary, body, status, started_at, completed_at, featured, cover_media_id | slug唯一；status/featured/sort索引 |
| `project_links` | project_id, link_type, url, label, sort_order | project/sort索引 |
| `project_media` | project_id, media_id, caption, sort_order | project/sort联合索引 |
| `moments` | body, mood, status, published_at, author_id | status/published索引 |
| `moment_media` | moment_id, media_id, sort_order | moment/sort联合索引 |

### 2.4 相册与媒体

| 实体 | 关键字段 | 关键约束/索引 |
| --- | --- | --- |
| `media` | storage_path, original_name, mime_type, size, width, height, sha256, alt_text, created_by | storage_path唯一；sha256索引 |
| `media_variants` | media_id, variant, path, width, height, size | media/variant唯一 |
| `albums` | title, slug, description, status, cover_media_id, sort_order | slug唯一；status/sort索引 |
| `album_photos` | album_id, media_id, caption, taken_at, location, sort_order | album/sort索引 |

### 2.5 互动

| 实体 | 关键字段 | 关键约束/索引 |
| --- | --- | --- |
| `comments` | target_type, target_id, parent_id, nickname, contact, body, status, ip_hash, created_at | target/status/time索引 |
| `guestbook_entries` | parent_id, nickname, contact, body, status, pinned, created_at | status/pinned/time索引 |
| `link_categories` | name, slug, sort_order | slug唯一 |
| `friend_links` | category_id, name, url, avatar_path, description, status, sort_order, last_checked_at | url唯一；status/sort索引 |
| `friend_link_applications` | name, url, contact, description, status, reviewer_id, reviewed_at | status/time索引 |
| `reports` | target_type, target_id, reason, status, created_at | status/time索引 |

### 2.6 页面与配置

| 实体 | 关键字段 | 关键约束/索引 |
| --- | --- | --- |
| `pages` | title, slug, body_source, body_html, status, seo_config | slug唯一；status索引 |
| `navigation_items` | parent_id, label, url, icon, target, sort_order, is_visible | parent/sort索引 |
| `home_modules` | module_type, title, enabled, sort_order, config_json | enabled/sort索引 |
| `site_settings` | key, value_json, is_public, updated_by | key唯一 |
| `backup_records` | filename, size, checksum, status, created_by, created_at | time索引 |

## 3. 内容状态

### 3.1 发布状态

- `draft`：仅作者和有权限的后台用户可见。
- `scheduled`：到达发布时间后由查询规则或本地维护任务公开。
- `published`：公开展示。
- `archived`：保留访问或从列表隐藏，按内容配置决定。
- `trashed`：回收站状态，不公开。

### 3.2 审核状态

- `pending`：等待审核。
- `approved`：允许公开。
- `rejected`：拒绝但保留审核记录。
- `spam`：垃圾内容。
- `hidden`：曾公开但被管理员隐藏。

## 4. 角色定义

| 角色 | 定位 |
| --- | --- |
| 超级管理员 | 所有权限，包括用户、角色、安全、备份和恢复 |
| 管理员 | 管理全部内容和审核，可执行普通维护，不可修改超级管理员关键权限 |
| 编辑 | 编辑、发布站点内容和处理审核，不能管理用户、安全与备份 |
| 作者 | 创建和维护自己的文章、项目与动态，发布需根据权限决定 |

访客不是后台用户角色，不进入用户表即可完成公开浏览与匿名提交。

## 5. 权限代码

权限使用稳定代码，路由、模板和服务层共用：

- `dashboard.view`
- `post.view_admin`, `post.create`, `post.edit_any`, `post.edit_own`, `post.publish`, `post.delete`
- `taxonomy.manage`
- `profile.manage`, `project.manage`, `moment.manage`, `gallery.manage`
- `media.upload`, `media.manage`, `media.delete`
- `comment.moderate`, `guestbook.moderate`, `friend_link.manage`
- `appearance.manage`, `seo.manage`, `settings.manage`
- `user.manage`, `role.manage`, `audit.view`
- `backup.create`, `backup.verify`, `backup.restore`
- `system.maintain`

## 6. 权限矩阵

| 能力 | 超级管理员 | 管理员 | 编辑 | 作者 |
| --- | --- | --- | --- | --- |
| 查看仪表盘 | 是 | 是 | 是 | 是 |
| 创建文章 | 是 | 是 | 是 | 是 |
| 编辑任意文章 | 是 | 是 | 是 | 否 |
| 编辑自己的文章 | 是 | 是 | 是 | 是 |
| 发布文章 | 是 | 是 | 是 | 默认否 |
| 永久删除内容 | 是 | 可配置 | 否 | 否 |
| 管理分类标签 | 是 | 是 | 是 | 否 |
| 管理个人资料/项目/动态 | 是 | 是 | 是 | 自己内容 |
| 上传媒体 | 是 | 是 | 是 | 是 |
| 删除被引用媒体 | 是 | 可配置 | 否 | 否 |
| 审核互动内容 | 是 | 是 | 是 | 否 |
| 管理首页/导航/主题 | 是 | 是 | 可配置 | 否 |
| 管理用户与角色 | 是 | 可创建普通账号 | 否 | 否 |
| 查看审计日志 | 是 | 是 | 否 | 否 |
| 创建和校验备份 | 是 | 可配置 | 否 | 否 |
| 执行恢复 | 是 | 否 | 否 | 否 |

## 7. 数据保留与删除

- 文章、页面、项目和相册先进入回收站，永久删除需更高权限和二次确认。
- 审计日志不得通过普通内容删除流程修改。
- 媒体删除前检查引用；存在引用时默认禁止删除。
- 访客联系方式可在审核完成后按配置脱敏或定期清理。
- 备份记录删除不等于直接删除备份文件，文件操作必须单独校验目标路径。
- 所有级联删除策略在迁移与测试中明确，避免SQLite默认行为导致孤立记录。

## 8. SQLite迁移原则

- 每次模型变化生成可审查的迁移文件。
- SQLite不支持的复杂表结构变化使用批处理迁移模式。
- 生产迁移前创建一致性备份并验证可恢复。
- 迁移不与应用多进程同时写入数据库。
- 大数据迁移分批执行，记录耗时和磁盘空间要求。
