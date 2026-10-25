# saubakaの博客 / Baka Blog

一个轻量的个人博客：**Flask + SQLite** 做后端，**Vue 3** 做前台和后台。前台只有「首页 / 博客 / 动态」，访客完全不能写入（没有评论、留言、点赞、账号）；视觉是极浅蓝、浅灰、浅粉的手账风格，没有深色块，文字和卡片随滚动位置入场、离场。

```
backend/    Flask API、SQLite、Markdown 与图片流水线、备份恢复、CLI（flask --app app …）
frontend/   Vite 工程：前台 public.html、后台 admin.html、后台预览框 preview.html
deploy/     systemd 单元、nginx 示例、部署 / 回滚 / 恢复演练 / 排练脚本
docs/       计划、各部分说明、接口文档与真实样例
design/     阶段 0 的静态设计样张
scripts/    QA 实例脚本
```

## 文档

| 文件 | 内容 |
|---|---|
| [docs/PLAN.md](docs/PLAN.md) | 已确认的完整规划与里程碑 |
| [docs/BACKEND.md](docs/BACKEND.md) · [docs/API.md](docs/API.md) | 后端结构、每个接口（与路由一一对应，有测试盯着）、`docs/api-samples/` 真实样例 |
| [docs/FRONTEND.md](docs/FRONTEND.md) | 前台：数据流、滚动动效引擎、样式与 CSP 规则、检查、体积 |
| [docs/ADMIN.md](docs/ADMIN.md) | 后台：结构、编辑器、预览框、覆盖表、检查、没做的事 |
| [deploy/README.md](deploy/README.md) | 部署、更新、回滚、恢复、排练 |

## 开发

```bash
cd backend  && make venv && make seed OWNER=me PASSWORD=…   # 示例内容 + 管理员（仅开发）
cd frontend && npm install && npm run build
make -C backend serve                                        # http://127.0.0.1:5300  （后台在 /admin）
cd frontend && npm run dev                                   # http://127.0.0.1:5173  热更新，/api 代理到 :5300
```

**本机一键面板（macOS）**：双击项目根目录的 `run-local.command`（或运行 `scripts/panel.sh`），用数字菜单启动 / 停止 / 重启 / 看状态和日志 / 打开浏览器 / 重新构建前端 / 灌示例内容 / 管理测试用的后台实例 / 登录后自动启动。`scripts/panel.sh start|stop|restart|status|logs|open|build|seed` 也可以直接当命令用。服务在后台运行，关掉终端窗口不会停。首选端口是 5300；被别的程序占着时自动顺延到 5301、5302 …（最多往后 20 个，跳过 5310 的测试实例和 5173 的前端热更新），实际用的端口显示在菜单顶部的“地址 / 端口”那一行，停止 / 状态 / 打开浏览器都按它走（`BAKA_PANEL_PORT` 可以换首选端口）。面板只管本机的开发 / 预览服务，线上服务器的更新是 `deploy/deploy.sh`。

## 检查

```bash
make check       # 后端 ruff + 测试，前端类型 + lint + 单元测试
make qa          # 前台浏览器检查（Chromium + WebKit）：溢出、线与阴影、对比度、聚焦环、导航指示器、动效、CSP、无障碍、流程
make qa-admin    # 后台浏览器检查（单独的 QA 实例）
cd frontend && npm run qa:perf   # 手机 Slow 4G + 4 倍降速的 LCP / CLS
make rehearse    # 在临时目录里排练安装、更新、四种失败回滚和恢复演练
```

## 版本与状态

当前 0.5.1。P0 设计、P1 后端、P2 前台、P3 后台、P4 打磨、P5 部署材料已完成并自动化验证（Chromium + WebKit），已部署并对外开放。还没有在真实 Safari 和手机上验收（Playwright 的 WebKit 与 Safari 同源，但不是同一个构建）。详见各文档里的「局限」。
