# 阶段六数据模型与公开规则

## 模型映射

| 模型 | 前台 | 后台 |
| --- | --- | --- |
| `SiteProfile` | 首页欢迎区、关于页 | 个人资料 |
| `PersonalSkill`、`Experience`、`PersonalGoal`、`SocialLink` | 关于页 | 个人内容编辑 |
| `Project` | 项目列表与详情 | 项目作品管理 |
| `Moment` | 动态列表与详情 | 生活动态管理 |
| `HomeModule`、`SiteSetting` | 首页与页脚 | 首页与导航配置 |
| `NavigationItem` | 顶部/页脚导航 | 自定义导航管理 |
| `CustomPage` | `/pages/<slug>/` | 独立页面管理 |

## 公开规则

- 项目必须是`published`且未软删除。
- 动态必须是`published`且未软删除。
- 独立页面必须是`published`；只有同时开启导航展示才加入顶部导航。
- 个人条目只有`is_visible`为真时显示。
- 首页只加载`is_enabled`为真的模块，并按`sort_order`排序。

## 性能策略

- 列表分页；首页只按每个模块的`item_limit`加载数据。
- 公开状态、发布时间、软删除、排序和slug均建立必要索引。
- 内容继续采用服务端渲染和本地静态资源，没有新增前端框架或远程依赖。
