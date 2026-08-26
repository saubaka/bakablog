# baka blog 更新包

后台固定从 `updates/stable.json` 对应的 GitHub Raw 地址读取稳定版清单。当前版本清单可以不带 `package`；发布新版本时先运行根目录的 `scripts/build_update_package.py`，把生成的 ZIP 上传到同版本 GitHub Release，再把脚本输出的 `package` 节点写入清单并提交。

更新 ZIP 只允许两个顶层内容：

- `update.json`：格式版本与目标应用版本。
- `payload/`：覆盖到项目暂存副本的完整发布文件。

Linux 管理器会再次验证下载地址、声明体积、SHA-256、ZIP 路径、符号链接、文件数量与展开体积。安装前会检查磁盘空间并创建代码与站点数据备份；依赖安装、数据库迁移、系统检查或健康检查失败时自动恢复。

管理员后台不直接执行 root 命令，只写入固定格式的 `request.json`。由 `bakablog-update.path` 触发 root 管理器处理，避免 Web 进程获得系统写权限。
