# 安全与依赖审计

## 信任边界

- 访客输入：公开表单、查询参数、评论、留言和友链申请均视为不可信。
- 管理入口：后台默认只允许已登录用户，并在路由与写操作处校验权限和CSRF。
- 文件输入：只接受受控大小的JPEG、PNG、WebP；通过Pillow读取真实内容、重新编码、移除元数据并生成本地WebP缩略图。
- 网络输入：友链检查只允许HTTP(S)标准端口和公网地址，每次重定向重新验证，拒绝本机、内网和特殊地址。
- 归档输入：恢复前限制成员路径、类型、数量和总解压体积，拒绝路径穿越、重复路径、符号链接、加密成员和额外数据库路径。

## 已实施控制

- 生产密钥至少32字符且禁止默认值；站点地址必须是无凭据、无路径的HTTP或HTTPS origin。
- 默认接受任意Host/IP和HTTP；后台“站点管理 → 域名与协议”可保存精确Host、IP或子域通配规则，并可强制HTTPS。应用不提供绕过访问限制的公开恢复入口，变更前必须保留当前Host并确认TLS可用。
- 默认HTTP模式下Session和Remember Cookie启用`HttpOnly`和`SameSite=Lax`但不能启用`Secure`；切换HTTPS时应同时完成代理TLS复验。登录前清除旧会话，Flask-Login使用`strong`会话保护。
- 登录按规范化用户名和请求指纹限制为15分钟5次；日志只保留HMAC请求指纹，不存原始IP。
- 全站返回CSP、`X-Content-Type-Options`、`Referrer-Policy`、`Permissions-Policy`、`X-Frame-Options`与跨源资源策略；仅在后台启用强制HTTPS后加入升级策略和一年HSTS。
- 动态HTML和后台禁止缓存；静态文件与合法本地媒体使用版本化长缓存和条件请求。
- 请求ID只接受最长64位的安全字符，否则重新生成；日志包含请求ID、方法、路径、状态与耗时，不写密码、Cookie和密钥。
- 表单内存、字段数、总上传体积和备份展开体积均有上限；413同时提供HTML和JSON错误边界。
- Markdown经过Bleach白名单过滤；文章图片只允许本地媒体地址；危险协议不会进入导航和社交链接。

## 依赖检查

`requirements.txt`和`requirements-dev.txt`均为精确版本，运行依赖可从项目`wheelhouse/`离线安装。2026-07-16执行`pip check`无损坏依赖。对关键公告的点检结果：

- Flask固定为3.1.3，覆盖CVE-2026-27205所述的3.1.3之前版本问题：<https://nvd.nist.gov/vuln/detail/CVE-2026-27205>
- Pillow固定为12.3.0，覆盖CVE-2026-59203、CVE-2026-40192和CVE-2026-25990所述旧版本问题：<https://nvd.nist.gov/vuln/detail/CVE-2026-59203>、<https://nvd.nist.gov/vuln/detail/CVE-2026-40192>、<https://nvd.nist.gov/vuln/detail/CVE-2026-25990>
- Jinja2固定为3.1.6，覆盖CVE-2025-27516所述3.1.6之前版本问题：<https://nvd.nist.gov/vuln/detail/CVE-2025-27516>
- Waitress固定为3.0.2，覆盖CVE-2024-49769所述3.0.1之前版本问题：<https://nvd.nist.gov/vuln/detail/CVE-2024-49769>

该检查是发布时点抽查，不等同于永久无漏洞声明。每次升级前应在隔离副本运行`pip check`、自动化测试、公告复核和恢复演练。当前本机Python为3.14.0rc2，只用于验证；生产必须选择仍受支持的稳定版Python，并重新建立与该平台匹配的本地虚拟环境和wheelhouse。

## 仍需环境控制

- 管理员使用独立长密码和密码管理器；不共享账号。
- 反向代理只监听公网80/443，Waitress/Gunicorn只绑定`127.0.0.1`。
- 实例目录只授予应用服务账号读写，源码和代理配置只授予部署账号修改。
- 防火墙不开放SQLite、实例目录或WSGI内部端口。
- 每日备份至少复制一份到与主机故障域不同、访问受控的位置，并定期验证哈希和恢复。
