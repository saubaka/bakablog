# 阶段九：安全、测试与部署上线

阶段九基础工作已完成，当前维护版本为`1.48.0`。Windows只做Flask本地测试；正式部署推荐Debian 12，也支持macOS登录用户下的LaunchAgent部署。前台不提供登录、注册、个人中心或普通用户模块；唯一的超级管理员从`/bakaadmin`进入后台，并通过本地图片人机验证和按访问来源计算的密码失败次数限制。没有活动管理员时，打开站点任意页面都会直接进入唯一管理员创建指引（健康检查与静态资源仍放行）；远程或生产环境还需要命令行签发的一次性初始化口令。管理员重置只撤销管理员身份、密码、会话、令牌、恢复码和2FA，不删除普通用户或内容。文章与动态分别控制是否允许评论，开启后评论表单才会显示并接受提交。前台与后台由最终小窗主题层统一雾白、云朵蓝、花瓣粉、浅蓝轮廓、石墨蓝灰和晴蓝视觉；1.37.0至1.41.0已完成项目8移植第一至五阶段的主题基线、统一控件运动、顶部水滴通知与弹窗统一、同壳增强导航，以及后台通知动效设置与长尾清理。页面不再提供手动动效切换，但继续尊重系统“减少动态效果”偏好。

Windows默认入口为项目根目录的`start.bat`。它仅使用CMD和本地资源，支持`--check-only`预检，不修改执行策略、不提权、不联网下载，并在启动Flask时关闭调试器和自动重载。

## 交付索引

- [安全与依赖审计](security-and-release.md)
- [Windows本地测试](../windows-local-testing.md)
- [Linux部署](deployment-linux.md)
- [macOS部署](deployment-macos.md)
- [运维、监控与回滚](operations.md)
- [管理员使用说明](admin-guide.md)
- [发布验证报告](validation.md)
- [项目8移植六阶段规划](project8-ui-motion-adoption-plan.md)
- [项目8移植第一阶段验收](project8-phase1-validation.md)
- [项目8移植第二阶段验收](project8-phase2-validation.md)
- [项目8移植第三阶段验收](project8-phase3-validation.md)
- [项目8移植第四阶段验收](project8-phase4-validation.md)
- [项目8移植第五阶段验收](project8-phase5-validation.md)
- [项目8移植第六阶段验收](project8-phase6-validation.md)
- [更淡的浅蓝配色（1.43.0）](light-blue-scheme-validation.md)
- [初始化页重构（1.44.0→1.48.0）](setup-page-redesign.md)
- [单线条物理阻尼动效重构规划](single-line-physical-damping-motion-plan.md)
- [右下角浮层、后台视觉与管理员初始化重构规划](motion-switch-notification-dialog-admin-bootstrap-plan.md)

## 发布边界

代码、配置、空实例迁移、恢复演练和浏览器回归已通过。当前没有用户的Debian服务器权限，因此没有修改公网环境，也不把Windows本机验证描述为公网已上线。将`.env.production.example`中的占位值替换为真实环境变量并按Debian文档接入，才是正式发布。

SQLite继续限定为单机、读多写少部署。应用实例和定时维护必须指向同一块持久化本地磁盘；不得同时启动多个写入主机或把SQLite文件放在不可靠的网络共享目录。

## v1.26.0全站搜索维护项

独立`/search/`页面统一检索公开博客、项目、动态、友链和留言，并提供严格/自由匹配、数字分页和约一秒输入防抖。正式SQLite已升级到迁移`e5c7a9b2d413`，由FTS5 trigram索引和15个触发器保持五类内容同步；不支持FTS5时服务会自动使用参数化LIKE降级查询。当前干净状态备份位于`instance/backups/cloudtrace-clean-1.26.0-20260728.zip`。

## v1.27.0第三方链接维护项

前台所有HTTP/HTTPS站外链接统一经过`/out/`本地提示页；富文本中的裸网址在服务端输出时补全，动态插入的普通文本和已有外链由本地脚本继续接管。后台“站点 → 第三方链接”按主机名维护安全与危险规则，未登记主机默认显示安全性未知。提示页发送`no-store`、`no-referrer`和`noindex`响应头，只接受规范化HTTP/HTTPS地址，不允许账号密码型URL。正式SQLite迁移头为`b7d2f0a64e19`。
