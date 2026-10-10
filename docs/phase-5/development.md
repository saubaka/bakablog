# 阶段五开发与使用说明

## 数据库升级

已有站点更新代码和本地依赖后执行：

```powershell
.\scripts\bootstrap.ps1 -Offline
.\.venv\Scripts\python.exe -m flask --app wsgi:app db upgrade
```

首次部署仍可使用`.\scripts\init-site.ps1`。最新迁移会建立博客表、索引、FTS5虚拟表和增删改同步触发器。

## 日常发布流程

1. 从`/bakaadmin`登录，进入“文章管理”。
2. 在“分类与标签”中预先建立分类，或在编辑器标签栏输入新标签。
3. 新建文章并填写标题、摘要和Markdown正文；图片通过“插入图片”写入本地媒体库。
4. 选择草稿、立即发布或定时发布。手动保存会创建版本快照，已有文章输入停止约1.2秒后自动保存正文。
5. 使用后台预览检查排版；发布后从公开博客、分类标签、归档、订阅和站点地图访问。

## Markdown能力

- 支持标题、列表、表格、链接、引用、围栏代码块和脚注。
- 代码块使用Pygments在服务端生成高亮HTML，无需前端CDN。
- 提示块语法使用Python-Markdown admonition扩展。
- HTML经过Bleach白名单净化；脚本、事件属性和危险协议不会进入公开正文。

## 站点地址

生产环境设置`CLOUD_DIARY_SITE_URL=https://example.com`，供canonical、Atom和站点地图生成绝对地址。不要包含末尾斜杠。

## 搜索降级

标准SQLite构建使用FTS5；自定义SQLite若不支持FTS5，迁移会保留其余博客结构，搜索服务自动改用标题、摘要和正文的`LIKE`查询。该回退适合个人站点规模，但大数据量性能低于FTS5。
